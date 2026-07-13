"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

const runtimeDir = __dirname;
const stagingRoot = path.resolve(runtimeDir, "sources", "staging");
const testRoot = path.resolve(stagingRoot, `hushplayer_protocol_${process.pid}`);

async function main() {
    fs.mkdirSync(testRoot, { recursive: true });
    const pluginPath = path.join(testRoot, "open_fixture.js");
    const fallbackPluginPath = path.join(testRoot, "fallback_fixture.js");
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
    const relativePlugin = path.relative(runtimeDir, pluginPath).replaceAll("\\", "/");
    const relativeFallbackPlugin = path.relative(runtimeDir, fallbackPluginPath).replaceAll("\\", "/");
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

    const child = spawn(process.execPath, [path.join(runtimeDir, "runner.js")], {
        cwd: runtimeDir,
        env: { ...process.env, HUSHPLAYER_SOURCE_REGISTRY: registryPath },
        windowsHide: true,
        stdio: ["pipe", "pipe", "pipe"],
    });
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
            const resolve = pending.get(response.id);
            if (resolve) {
                pending.delete(response.id);
                resolve(response);
            }
        }
    });

    let id = 1;
    const request = (action, payload = {}) => new Promise((resolve) => {
        const requestId = id++;
        pending.set(requestId, resolve);
        child.stdin.write(`${JSON.stringify({ id: requestId, action, ...payload })}\n`);
    });

    const sources = await request("listSources");
    assert.equal(sources.success, true);
    assert.equal(sources.data[0].capabilities.playback, true);
    assert.equal(sources.data[0].capabilities.download, true);
    assert.equal(sources.data[1].capabilities.playback, true);
    assert.equal(sources.data[1].capabilities.download, true);
    assert.equal(sources.data[1].capabilities.downloadViaPlayback, true);
    assert.equal(sources.data[2].capabilities.playback, false);

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
    await new Promise((resolve, reject) => {
        child.once("close", (code) => code === 0 ? resolve() : reject(new Error(`runner exit ${code}`)));
    });
    process.stdout.write("playback protocol self-test: OK\n");
}

main()
    .catch((error) => {
        process.stderr.write(`${error.stack || error}\n`);
        process.exitCode = 1;
    })
    .finally(() => {
        if (testRoot.startsWith(`${stagingRoot}${path.sep}`)) {
            fs.rmSync(testRoot, { recursive: true, force: true });
        }
    });
