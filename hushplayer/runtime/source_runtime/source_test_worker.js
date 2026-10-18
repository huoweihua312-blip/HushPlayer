"use strict";

const host = require("./plugin_host");

async function measure(label, callback) {
    const startedAt = Date.now();

    try {
        const data = await callback();
        return {
            status: "passed",
            elapsedMs: Date.now() - startedAt,
            data,
            error: "",
        };
    } catch (error) {
        return {
            status: "failed",
            elapsedMs: Date.now() - startedAt,
            data: null,
            error: error?.message || String(error),
        };
    }
}

async function main() {
    const sourceId = String(process.argv[2] || "").trim();
    const keyword = String(process.argv.slice(3).join(" ") || "测试").trim();

    if (!sourceId) {
        throw new Error("缺少 sourceId");
    }

    const result = {
        sourceId,
        playbackTested: false,
        playbackDisabledReason: "本阶段不测试或解析商业音源播放地址",
        load: null,
        search: null,
        metadata: null,
        lyric: null,
    };
    let firstItem = null;

    result.load = await measure("load", async () => {
        const loaded = await host.loadPlugin(sourceId, { allowDisabled: true });
        return {
            platform: loaded.plugin.platform || loaded.source.platform || loaded.source.name,
            author: loaded.plugin.author || loaded.source.author || "",
            version: loaded.plugin.version || loaded.source.version || "",
            sha256: loaded.sha256,
            requiredModules: loaded.requiredModules,
            capabilities: loaded.capabilities,
        };
    });

    if (result.load.status === "passed" && result.load.data.capabilities.search) {
        result.search = await measure("search", async () => {
            const items = await host.search(sourceId, keyword, 1, "music", { allowDisabled: true });
            firstItem = items[0] || null;
            return {
                count: items.length,
                firstItem,
            };
        });
    } else {
        result.search = { status: "skipped", elapsedMs: 0, data: null, error: "没有搜索接口" };
    }

    if (firstItem && result.load.data.capabilities.metadata) {
        result.metadata = await measure("metadata", () =>
            host.getMetadata(sourceId, firstItem, { allowDisabled: true })
        );
    } else {
        result.metadata = { status: "skipped", elapsedMs: 0, data: null, error: "没有元数据接口或搜索结果" };
    }

    if (firstItem && result.load.data.capabilities.lyrics) {
        result.lyric = await measure("lyric", async () => {
            const lyric = await host.getLyric(sourceId, firstItem, { allowDisabled: true });
            return {
                available: lyric.available,
                length: lyric.rawLrc.length,
            };
        });
    } else {
        result.lyric = { status: "skipped", elapsedMs: 0, data: null, error: "没有歌词接口或搜索结果" };
    }

    process.stdout.write(`${JSON.stringify(result)}\n`);
    await host.unloadAllSources();
    host.terminateProcess(0);
}

main().catch((error) => {
    host.log(error?.stack || error);
    host.terminateProcess(1);
});
