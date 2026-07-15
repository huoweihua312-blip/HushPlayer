"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

const runtimeDir = __dirname;
const stagingRoot = path.resolve(runtimeDir, "sources", "staging");
const testRoot = path.resolve(stagingRoot, `hushplayer_protocol_${process.pid}`);
const requestTimeoutMs = 5000;
const shutdownTimeoutMs = 2000;
let runnerChild = null;

function hasExited(child) {
    return child.exitCode !== null || child.signalCode !== null;
}

function waitForChildExit(child, timeoutMs) {
    if (hasExited(child)) return Promise.resolve(true);
    return new Promise((resolve) => {
        let settled = false;
        const finish = (exited) => {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            child.off("close", onClose);
            resolve(exited);
        };
        const onClose = () => finish(true);
        const timer = setTimeout(() => finish(false), timeoutMs);
        child.once("close", onClose);
        if (hasExited(child)) finish(true);
    });
}

async function stopRunnerChild(child) {
    if (!child || hasExited(child)) return;
    if (child.stdin?.writable) {
        try {
            child.stdin.write(`${JSON.stringify({ id: 0, action: "shutdown" })}\n`);
        } catch {
            // Fall through to the bounded forced termination below.
        }
    }
    if (await waitForChildExit(child, shutdownTimeoutMs)) return;
    child.kill();
    if (await waitForChildExit(child, shutdownTimeoutMs)) return;
    throw new Error(`runner process ${child.pid} could not be terminated`);
}

async function main() {
    fs.mkdirSync(testRoot, { recursive: true });
    const managedSourceRoot = path.join(testRoot, "sources", "active");
    fs.mkdirSync(managedSourceRoot, { recursive: true });
    const pluginPath = path.join(managedSourceRoot, "open_fixture.js");
    const fallbackPluginPath = path.join(managedSourceRoot, "fallback_fixture.js");
    const registryPath = path.join(testRoot, "registry.json");
    fs.writeFileSync(
        pluginPath,
        `module.exports = {
            search: async () => [{ id: "fixture", title: "Fixture" }],
            resolvePlayback: async (track) => {
                if (track.mode === "nonobject") return "not-an-object";
                if (track.mode === "invalid") return { url: "file:///private/audio.mp3" };
                return { url: "http://127.0.0.1:8765/audio.mp3", headers: {}, quality: "standard" };
            },
            resolveDownload: async () => ({
                url: "https://127.0.0.1:8765/audio.mp3", headers: {}, filename: "fixture.mp3"
            }),
            getLyric: async () => ({
                data: { syncedLyrics: "[00:00.00]Fixture lyric" }
            })
        };\n`,
        "utf8"
    );
    fs.writeFileSync(
        fallbackPluginPath,
        `module.exports = {
            search: async () => [{ id: "fallback", title: "Fallback" }],
            getMediaSource: async () => ({
                url: "http://127.0.0.1:8765/fallback.ogg", headers: { Referer: "https://example.invalid/" }
            })
        };\n`,
        "utf8"
    );
    const relativePlugin = path.relative(testRoot, pluginPath).replaceAll("\\", "/");
    const relativeFallbackPlugin = path.relative(testRoot, fallbackPluginPath).replaceAll("\\", "/");
    fs.writeFileSync(
        registryPath,
        JSON.stringify({
            version: 1,
            sources: [
                {
                    id: "open_fixture",
                    name: "Open fixture",
                    filename: relativePlugin,
                    enabled: true,
                    contentPolicy: "open",
                    capabilities: { search: true, playback: true, download: true },
                },
                {
                    id: "fallback_fixture",
                    name: "Fallback fixture",
                    filename: relativeFallbackPlugin,
                    enabled: true,
                    userInstalled: true,
                    sourceUrl: "https://example.invalid/fallback.js",
                    contentPolicy: "open",
                    capabilities: {
                        search: true,
                        playback: true,
                        download: true,
                        downloadViaPlayback: true,
                    },
                },
                {
                    id: "unknown_fixture",
                    name: "Unknown fixture",
                    filename: relativePlugin,
                    enabled: true,
                    contentPolicy: "unknown",
                    capabilities: { search: true, playback: true, download: true },
                },
            ],
        }),
        "utf8"
    );

    runnerChild = spawn(process.execPath, [path.join(runtimeDir, "runner.js")], {
        cwd: runtimeDir,
        env: { ...process.env, HUSHPLAYER_SOURCE_REGISTRY: registryPath },
        windowsHide: true,
        stdio: ["pipe", "pipe", "pipe"],
    });
    const child = runnerChild;
    child.stdout.setEncoding("utf8");
    let buffer = "";
    const pending = new Map();
    child.stdout.on("data", (chunk) => {
        buffer += chunk;
        while (buffer.includes("\n")) {
            const index = buffer.indexOf("\n");
            const line = buffer.slice(0, index).trim();
            buffer = buffer.slice(index + 1);
            if (!line) continue;
            const response = JSON.parse(line);
            const requestState = pending.get(response.id);
            if (requestState) {
                pending.delete(response.id);
                clearTimeout(requestState.timer);
                requestState.resolve(response);
            }
        }
    });

    const rejectPending = (error) => {
        for (const requestState of pending.values()) {
            clearTimeout(requestState.timer);
            requestState.reject(error);
        }
        pending.clear();
    };
    child.once("error", (error) => rejectPending(error));
    child.once("close", (code, signal) => {
        rejectPending(new Error(`runner exited before responding: code=${code} signal=${signal}`));
    });

    let id = 1;
    const request = (action, payload = {}) => new Promise((resolve, reject) => {
        const requestId = id++;
        const timer = setTimeout(() => {
            pending.delete(requestId);
            reject(new Error(`runner request timed out: ${action}`));
        }, requestTimeoutMs);
        pending.set(requestId, { resolve, reject, timer });
        try {
            child.stdin.write(
                `${JSON.stringify({ id: requestId, action, ...payload })}\n`,
                (error) => {
                    if (!error || !pending.has(requestId)) return;
                    pending.delete(requestId);
                    clearTimeout(timer);
                    reject(error);
                }
            );
        } catch (error) {
            pending.delete(requestId);
            clearTimeout(timer);
            reject(error);
        }
    });

    const sources = await request("listSources");
    assert.equal(sources.success, true);
    const sourceById = Object.fromEntries(sources.data.map((source) => [source.id, source]));
    const sourceDiagnostics = JSON.stringify(sources.data, null, 2);
    assert.equal(sourceById.open_fixture.capabilities.playback, true, sourceDiagnostics);
    assert.equal(sourceById.open_fixture.capabilities.download, true);
    assert.equal(sourceById.fallback_fixture.capabilities.playback, true);
    assert.equal(sourceById.fallback_fixture.capabilities.download, true);
    assert.equal(sourceById.fallback_fixture.capabilities.downloadViaPlayback, true);
    assert.equal(sourceById.unknown_fixture.capabilities.playback, false);
    assert.equal(sourceById.unknown_fixture.capabilities.download, false);
    if (process.env.HUSHPLAYER_PROTOCOL_FORCE_FAILURE === "1") {
        assert.fail("forced lifecycle cleanup failure");
    }

    const playback = await request("resolvePlayback", {
        sourceId: "open_fixture",
        track: { id: "fixture" },
        options: { quality: "standard" },
    });
    assert.equal(playback.success, true);
    assert.deepEqual(playback.data.headers, {});
    assert.equal(playback.data.seekable, true);

    const unsupported = await request("resolvePlayback", {
        sourceId: "unknown_fixture",
        track: { id: "fixture" },
    });
    assert.equal(unsupported.success, false);
    assert.match(unsupported.error.message, /未启用播放能力/);

    const invalid = await request("resolvePlayback", {
        sourceId: "open_fixture",
        track: { mode: "invalid" },
    });
    assert.equal(invalid.success, false);
    assert.match(invalid.error.message, /HTTP/);

    const nonobject = await request("resolvePlayback", {
        sourceId: "open_fixture",
        track: { mode: "nonobject" },
    });
    assert.equal(nonobject.success, false);
    assert.match(nonobject.error.message, /必须是对象/);

    const download = await request("resolveDownload", {
        sourceId: "open_fixture",
        track: { id: "fixture" },
    });
    assert.equal(download.success, true);
    assert.equal(download.data.filename, "fixture.mp3");

    const lyric = await request("getLyric", {
        sourceId: "open_fixture",
        musicItem: { id: "fixture" },
    });
    assert.equal(lyric.success, true);
    assert.equal(lyric.data.available, true);
    assert.equal(lyric.data.rawLrc, "[00:00.00]Fixture lyric");

    const fallbackDownload = await request("resolveDownload", {
        sourceId: "fallback_fixture",
        track: { id: "fallback" },
    });
    assert.equal(fallbackDownload.success, true);
    assert.equal(fallbackDownload.data.viaPlayback, true);
    assert.equal(fallbackDownload.data.headers.Referer, "https://example.invalid/");

    const directUrl = await request("search", {
        sourceId: "https://example.invalid/unsafe.js",
        keyword: "fixture",
    });
    assert.equal(directUrl.success, false);
    assert.match(directUrl.error.message, /必须先通过注册/);

    const shutdown = await request("shutdown");
    assert.equal(shutdown.success, true);
    assert.equal(await waitForChildExit(child, requestTimeoutMs), true);
    assert.equal(child.exitCode, 0);
    process.stdout.write("playback protocol self-test: OK\n");
}

main()
    .catch((error) => {
        process.stderr.write(`${error.stack || error}\n`);
        process.exitCode = 1;
    })
    .finally(async () => {
        try {
            await stopRunnerChild(runnerChild);
        } catch (error) {
            process.stderr.write(`runner cleanup failed: ${error.stack || error}\n`);
            process.exitCode = 1;
        }
        if (testRoot.startsWith(`${stagingRoot}${path.sep}`)) {
            fs.rmSync(testRoot, { recursive: true, force: true });
        }
    });
