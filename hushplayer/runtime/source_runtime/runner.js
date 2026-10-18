"use strict";

const path = require("node:path");
const readline = require("node:readline");
const { spawn } = require("node:child_process");
const host = require("./plugin_host");

const TEST_WORKER_PATH = path.join(__dirname, "source_test_worker.js");
const TEST_TIMEOUT_MS = 45000;
let shuttingDown = false;
const cancelledRequestIds = new Set();

function writeResponse(response) {
    process.stdout.write(`${JSON.stringify(host.serializable(response))}\n`);
}

function errorPayload(error) {
    return {
        message: error?.message || String(error),
        stack: error?.stack || "",
    };
}

function runSourceTest(sourceId, keyword = "测试") {
    return new Promise((resolve, reject) => {
        const child = spawn(process.execPath, [TEST_WORKER_PATH, sourceId, keyword], {
            cwd: __dirname,
            windowsHide: true,
            stdio: ["ignore", "pipe", "pipe"],
        });
        let stdout = "";
        let stderr = "";
        let finished = false;
        const timer = setTimeout(() => {
            if (finished) return;
            finished = true;
            child.kill();
            reject(new Error(`音源测试超时（${TEST_TIMEOUT_MS} ms）`));
        }, TEST_TIMEOUT_MS);

        child.stdout.setEncoding("utf8");
        child.stderr.setEncoding("utf8");
        child.stdout.on("data", (chunk) => {
            stdout += chunk;
        });
        child.stderr.on("data", (chunk) => {
            stderr += chunk;
            process.stderr.write(chunk);
        });
        child.on("error", (error) => {
            if (finished) return;
            finished = true;
            clearTimeout(timer);
            reject(error);
        });
        child.on("close", (code) => {
            if (finished) return;
            finished = true;
            clearTimeout(timer);

            if (code !== 0) {
                reject(new Error(stderr.trim() || `音源测试进程退出，代码 ${code}`));
                return;
            }

            const line = stdout
                .split(/\r?\n/)
                .map((item) => item.trim())
                .filter(Boolean)
                .at(-1);

            if (!line) {
                reject(new Error("音源测试进程没有返回结果"));
                return;
            }

            try {
                resolve(JSON.parse(line));
            } catch (error) {
                reject(new Error(`音源测试结果不是有效 JSON：${error.message}`));
            }
        });
    });
}

async function handleRequest(request) {
    const action = String(request?.action || "");

    switch (action) {
        case "ping":
            return {
                runnerVersion: "1.1.0",
                protocol: "jsonl-v1",
                playbackEnabled: true,
                downloadEnabled: true,
            };
        case "listSources":
            return host.listSources();
        case "search":
            return host.search(
                request.sourceId,
                request.keyword,
                request.page,
                request.type
            );
        case "getMetadata":
            return host.getMetadata(request.sourceId, request.musicItem);
        case "getLyric":
            return host.getLyric(request.sourceId, request.musicItem);
        case "resolvePlayback":
            return host.resolvePlayback(request.sourceId, request.track, request.options || {});
        case "resolveDownload":
            return host.resolveDownload(request.sourceId, request.track, request.options || {});
        case "cancel":
            {
                const requestId = Number(request.requestId);
                if (Number.isInteger(requestId) && requestId > 0) {
                    cancelledRequestIds.add(requestId);
                    const cleanup = setTimeout(() => cancelledRequestIds.delete(requestId), 60000);
                    cleanup.unref();
                }
            }
            return { cancelled: true };
        case "getMediaSource":
            throw new Error("在线播放接口已保留，但本阶段明确未启用商业音源播放解析");
        case "testSource":
            return runSourceTest(request.sourceId, request.keyword || "测试");
        case "reloadSource":
            if (request.sourceId) {
                await host.unloadSource(request.sourceId);
            } else {
                await host.unloadAllSources();
            }
            return host.listSources();
        case "shutdown":
            shuttingDown = true;
            await host.unloadAllSources();
            return { stopped: true };
        default:
            throw new Error(`不支持的操作：${action || "(空)"}`);
    }
}

async function processLine(line) {
    let request;

    try {
        request = JSON.parse(line);
    } catch (error) {
        writeResponse({
            id: null,
            success: false,
            error: { message: `请求不是有效 JSON：${error.message}` },
        });
        return;
    }

    const id = request?.id ?? null;

    try {
        const data = await handleRequest(request);
        if (cancelledRequestIds.delete(Number(id))) {
            return;
        }
        writeResponse({ id, success: true, data });

        if (request.action === "shutdown") {
            input.close();
            setImmediate(() => host.terminateProcess(0));
        }
    } catch (error) {
        if (cancelledRequestIds.delete(Number(id))) {
            return;
        }
        writeResponse({ id, success: false, error: errorPayload(error) });
    }
}

const input = readline.createInterface({
    input: process.stdin,
    crlfDelay: Infinity,
});

input.on("line", (line) => {
    const trimmed = line.trim();

    if (trimmed && !shuttingDown) {
        void processLine(trimmed);
    }
});

input.on("close", async () => {
    if (!shuttingDown) {
        shuttingDown = true;
        await host.unloadAllSources();
        host.terminateProcess(0);
    }
});

process.on("unhandledRejection", (error) => {
    host.log("Node runner 未处理的 Promise 错误：", error?.stack || error);
});

host.log("HushPlayer online source runner ready");
