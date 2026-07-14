"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const Module = require("node:module");
const path = require("node:path");

const RUNTIME_DIR = __dirname;
const PROJECT_ROOT = path.resolve(RUNTIME_DIR, "..");
const REGISTRY_PATH = process.env.HUSHPLAYER_SOURCE_REGISTRY
    ? path.resolve(process.env.HUSHPLAYER_SOURCE_REGISTRY)
    : path.join(RUNTIME_DIR, "source_registry.json");
const ALLOWED_SOURCE_ROOTS = [
    path.resolve(RUNTIME_DIR, "sources"),
    path.resolve(PROJECT_ROOT, "user_sources"),
];
const BLOCKED_MODULES = new Set([
    "fs",
    "node:fs",
    "child_process",
    "node:child_process",
    "worker_threads",
    "node:worker_threads",
]);
const REQUEST_TIMEOUT_MS = 20000;
const REAL_PROCESS_EXIT = process.exit.bind(process);
const REAL_PROCESS_KILL = process.kill.bind(process);
const ORIGINAL_MODULE_LOAD = Module._load;
const pluginCache = new Map();
let moduleGuardInstalled = false;

function log(...values) {
    const message = values
        .map((value) => {
            if (typeof value === "string") {
                return value;
            }

            try {
                return JSON.stringify(value);
            } catch {
                return String(value);
            }
        })
        .join(" ");

    process.stderr.write(`${message}\n`);
}

function redirectConsoleToStderr() {
    console.log = (...values) => log(...values);
    console.info = (...values) => log(...values);
    console.warn = (...values) => log(...values);
    console.error = (...values) => log(...values);
    console.debug = (...values) => log(...values);
}

function jsonToPlugin(data) {
    const url = String(data.url || "").trim();
    if (!url) throw new Error("JSON 中缺少 url 字段");
    return {
        search() {
            return [{
                id: data.id || "json_track",
                title: data.title || "未知歌曲",
                artist: data.artist || "",
                album: data.album || "",
                artwork: data.artwork || "",
                duration: data.duration || null,
            }];
        },
        resolvePlayback() {
            return { url, headers: data.headers || {} };
        },
        resolveDownload() {
            return { url, headers: data.headers || {} };
        },
        getMusicInfo() {
            return { title: data.title, artist: data.artist };
        },
    };
}

function installHostGuards() {
    if (moduleGuardInstalled) {
        return;
    }

    Module._load = function guardedModuleLoad(request, parent, isMain) {
        const parentFilename = path.resolve(String(parent?.filename || RUNTIME_DIR));
        const requestedDirectlyBySource = ALLOWED_SOURCE_ROOTS.some((root) =>
            isPathInside(parentFilename, root)
        );

        if (requestedDirectlyBySource && BLOCKED_MODULES.has(String(request))) {
            throw new Error(`音源禁止加载敏感模块：${request}`);
        }

        return ORIGINAL_MODULE_LOAD.call(this, request, parent, isMain);
    };

    process.exit = (code = 0) => {
        throw new Error(`音源尝试结束宿主进程：${code}`);
    };
    process.kill = () => {
        throw new Error("音源尝试结束系统进程");
    };
    moduleGuardInstalled = true;
}

function terminateProcess(code = 0) {
    process.exit = REAL_PROCESS_EXIT;
    process.kill = REAL_PROCESS_KILL;
    REAL_PROCESS_EXIT(code);
}

function installMusicFreeEnvironment() {
    if (global.env && typeof global.env === "object") {
        return;
    }

    const memoryCache = new Map();
    const userVariables = new Map();

    global.env = {
        getUserVariables() {
            return Object.fromEntries(userVariables.entries());
        },
        getUserVariable(key) {
            return userVariables.get(String(key));
        },
        setUserVariables(values) {
            if (values && typeof values === "object") {
                for (const [key, value] of Object.entries(values)) {
                    userVariables.set(key, value);
                }
            }
        },
        setUserVariable(key, value) {
            userVariables.set(String(key), value);
        },
        getCache(key) {
            return memoryCache.get(String(key));
        },
        setCache(key, value) {
            memoryCache.set(String(key), value);
        },
    };
}

function readRegistry() {
    if (!fs.existsSync(REGISTRY_PATH)) {
        throw new Error(`音源注册表不存在：${REGISTRY_PATH}`);
    }

    let parsed;

    try {
        parsed = JSON.parse(fs.readFileSync(REGISTRY_PATH, "utf8"));
    } catch (error) {
        throw new Error(`音源注册表无效：${error.message}`);
    }

    const sources = Array.isArray(parsed) ? parsed : parsed?.sources;

    if (!Array.isArray(sources)) {
        throw new Error("音源注册表必须包含 sources 数组");
    }

    return sources.filter((source) => source && typeof source === "object");
}

function findSource(sourceId) {
    const source = readRegistry().find((item) => item.id === sourceId);

    if (!source) {
        throw new Error(`没有找到音源：${sourceId}`);
    }

    return source;
}

function isPathInside(candidate, root) {
    const relative = path.relative(root, candidate);
    return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function resolveSourceFile(source) {
    const filename = String(source.filename || "").trim();

    if (!filename) {
        throw new Error(`音源 ${source.id} 没有 filename`);
    }

    const candidate = path.resolve(RUNTIME_DIR, filename);

    if (!ALLOWED_SOURCE_ROOTS.some((root) => isPathInside(candidate, root))) {
        throw new Error(`音源路径超出允许目录：${filename}`);
    }

    if (!fs.existsSync(candidate) || !fs.statSync(candidate).isFile()) {
        throw new Error(`音源文件不存在：${candidate}`);
    }

    return candidate;
}

function staticScanSource(filePath) {
    const stats = fs.statSync(filePath);

    if (stats.size <= 0 || stats.size > 2 * 1024 * 1024) {
        throw new Error(`音源文件大小不合理：${stats.size} 字节`);
    }

    const code = fs.readFileSync(filePath, "utf8");
    const beginning = code.slice(0, 1200).toLowerCase();

    if (beginning.includes("<html") || beginning.includes("<!doctype html")) {
        throw new Error("音源文件实际是 HTML 页面");
    }

    const requiredModules = new Set();
    const requirePattern = /require\s*\(\s*["']([^"']+)["']\s*\)/g;
    let match;

    while ((match = requirePattern.exec(code)) !== null) {
        requiredModules.add(match[1]);
    }

    const blocked = [...requiredModules].filter((name) => BLOCKED_MODULES.has(name));

    if (blocked.length) {
        throw new Error(`音源包含敏感依赖：${blocked.join(", ")}`);
    }

    const suspiciousPatterns = [
        /process\s*\.\s*mainModule/i,
        /process\s*\.\s*binding\s*\(/i,
        /process\s*\.\s*kill\s*\(/i,
        /(?:node:)?child_process/i,
        /(?:node:)?worker_threads/i,
    ];

    if (suspiciousPatterns.some((pattern) => pattern.test(code))) {
        throw new Error("音源包含敏感进程或模块访问代码");
    }

    return {
        code,
        requiredModules: [...requiredModules].sort(),
        sha256: crypto.createHash("sha256").update(Buffer.from(code, "utf8")).digest("hex"),
    };
}

function serializable(value, depth = 0, seen = new WeakSet()) {
    if (value === null || value === undefined) {
        return value ?? null;
    }

    if (["string", "number", "boolean"].includes(typeof value)) {
        return value;
    }

    if (typeof value === "bigint") {
        return value.toString();
    }

    if (typeof value === "function" || typeof value === "symbol" || depth > 8) {
        return undefined;
    }

    if (typeof value !== "object") {
        return String(value);
    }

    if (seen.has(value)) {
        return "[Circular]";
    }

    seen.add(value);

    if (Array.isArray(value)) {
        return value.slice(0, 200).map((item) => serializable(item, depth + 1, seen));
    }

    const result = {};

    for (const [key, item] of Object.entries(value)) {
        const normalized = serializable(item, depth + 1, seen);

        if (normalized !== undefined) {
            result[key] = normalized;
        }
    }

    return result;
}

function withTimeout(value, label, timeoutMs = REQUEST_TIMEOUT_MS) {
    let timer;
    const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(`${label}超时（${timeoutMs} ms）`)), timeoutMs);
    });

    return Promise.race([Promise.resolve(value), timeout]).finally(() => clearTimeout(timer));
}

function isContentPolicyAllowed(source) {
    return ["open", "user_owned"].includes(String(source?.contentPolicy || ""));
}

function capabilityMap(plugin, source) {
    const declared = source?.capabilities || {};
    const policyAllowed = isContentPolicyAllowed(source);
    const playbackMethod =
        typeof plugin?.resolvePlayback === "function" ||
        typeof plugin?.getMediaSource === "function";
    const downloadMethod =
        typeof plugin?.resolveDownload === "function" ||
        typeof plugin?.getDownloadSource === "function";
    const downloadViaPlayback =
        policyAllowed &&
        source?.userInstalled === true &&
        declared.downloadViaPlayback === true &&
        playbackMethod &&
        !downloadMethod;
    return {
        search: typeof plugin?.search === "function",
        metadata:
            typeof plugin?.getMusicInfo === "function" ||
            typeof plugin?.getMusicDetail === "function",
        lyrics: typeof plugin?.getLyric === "function",
        playback:
            policyAllowed &&
            declared.playback === true &&
            playbackMethod,
        download:
            policyAllowed &&
            declared.download === true &&
            (downloadMethod || downloadViaPlayback),
        downloadViaPlayback,
    };
}

function normalizeHeaders(value) {
    if (value === undefined || value === null) {
        return {};
    }

    if (typeof value !== "object" || Array.isArray(value)) {
        throw new Error("播放资源 headers 必须是对象");
    }

    const headers = {};
    for (const [key, item] of Object.entries(value)) {
        const name = String(key || "").trim();
        if (!name) {
            throw new Error("播放资源包含空 header 名称");
        }
        if (!["string", "number", "boolean"].includes(typeof item)) {
            throw new Error("播放资源 header 值必须是字符串或基础类型");
        }
        headers[name] = String(item);
    }
    return headers;
}

function normalizeResolvedResource(result, requestedQuality = "standard") {
    if (!result || typeof result !== "object" || Array.isArray(result)) {
        throw new Error("音源返回的播放资源必须是对象");
    }

    const url = String(result.url || "").trim();
    if (!url) {
        throw new Error("音源返回的播放资源缺少 URL");
    }

    let parsed;
    try {
        parsed = new URL(url);
    } catch {
        throw new Error("音源返回了无效的播放 URL");
    }
    if (!["http:", "https:"].includes(parsed.protocol)) {
        throw new Error("播放资源只允许 HTTP 或 HTTPS URL");
    }
    if (parsed.username || parsed.password) {
        throw new Error("播放资源 URL 不允许包含登录凭据");
    }

    return {
        url,
        headers: normalizeHeaders(result.headers),
        mimeType: String(result.mimeType || "").trim(),
        quality: String(result.quality || requestedQuality || "standard"),
        expiresAt: result.expiresAt ?? null,
        seekable: result.seekable !== false,
        filename: String(result.filename || "").trim(),
        title: displayText(result.title || result.name),
        artist: displayText(result.artist || result.artists || result.singer),
        album: displayText(result.album || result.albumName),
        artwork: displayText(
            result.artwork || result.coverImg || result.picUrl || result.pic || result.cover
        ),
        duration: normalizeDuration(result.duration || result.interval || result.time),
    };
}

async function unloadSource(sourceId) {
    const cached = pluginCache.get(sourceId);

    if (!cached) {
        return;
    }

    pluginCache.delete(sourceId);
    const dispose = cached.plugin?.dispose || cached.plugin?.onUnload;

    if (typeof dispose === "function") {
        try {
            await withTimeout(dispose.call(cached.plugin), `卸载音源 ${sourceId}`, 3000);
        } catch (error) {
            log(`卸载音源失败 ${sourceId}:`, error.message);
        }
    }

    if (cached.resolvedModule) {
        delete require.cache[cached.resolvedModule];
    }
}

async function unloadAllSources() {
    await Promise.all([...pluginCache.keys()].map((sourceId) => unloadSource(sourceId)));
}

async function loadPlugin(sourceId, options = {}) {
    if (typeof sourceId === "string" && (sourceId.startsWith("http://") || sourceId.startsWith("https://"))) {
        throw new Error("自定义 URL 必须先通过注册、静态扫描和受管理目录安装");
    }

    const source = findSource(sourceId);

    if (!source.enabled && !options.allowDisabled) {
        throw new Error(`音源已禁用：${source.name || source.id}`);
    }

    if (options.forceReload) {
        await unloadSource(sourceId);
    }

    if (pluginCache.has(sourceId)) {
        return pluginCache.get(sourceId);
    }

    const filePath = resolveSourceFile(source);
    const scan = staticScanSource(filePath);
    installHostGuards();
    installMusicFreeEnvironment();

    let resolvedModule = null;
    let plugin;

    try {
        if (path.extname(filePath).toLowerCase() === ".json") {
            plugin = jsonToPlugin(JSON.parse(scan.code));
        } else {
            resolvedModule = require.resolve(filePath);
            const exported = require(resolvedModule);
            plugin = exported?.default ?? exported;
        }
    } catch (error) {
        throw new Error(`加载音源失败：${error.message}`);
    }

    if (!plugin || (typeof plugin !== "object" && typeof plugin !== "function")) {
        throw new Error("音源导出内容无效");
    }

    const cached = {
        source,
        plugin,
        filePath,
        resolvedModule,
        sha256: scan.sha256,
        requiredModules: scan.requiredModules,
        capabilities: capabilityMap(plugin, source),
    };
    pluginCache.set(sourceId, cached);
    return cached;
}

function extractMusicItems(result) {
    if (Array.isArray(result)) return result;
    if (Array.isArray(result?.data)) return result.data;
    if (Array.isArray(result?.data?.data)) return result.data.data;
    if (Array.isArray(result?.list)) return result.list;
    if (Array.isArray(result?.musicList)) return result.musicList;
    return [];
}

function displayText(value, fallback = "") {
    if (Array.isArray(value)) {
        return value.map((item) => displayText(item)).filter(Boolean).join(" / ") || fallback;
    }

    if (value && typeof value === "object") {
        return String(value.name || value.title || value.value || fallback);
    }

    const text = String(value ?? "").trim();
    return text || fallback;
}

function normalizeDuration(value) {
    const duration = Number(value);

    if (!Number.isFinite(duration) || duration <= 0) {
        return null;
    }

    return duration > 10000 ? Math.round(duration / 1000) : Math.round(duration);
}

function normalizeMusicItem(source, item, capabilities = {}) {
    const raw = serializable(item) || {};
    return {
        sourceId: source.id,
        sourceName: source.name || source.platform || source.id,
        sourceUrl: String(source.sourceUrl || ""),
        id: displayText(item?.id || item?.musicId || item?.songId),
        songmid: displayText(item?.songmid || item?.mid),
        title: displayText(item?.title || item?.name, "未知歌曲"),
        artist: displayText(item?.artist || item?.artists || item?.singer, "未知艺术家"),
        album: displayText(item?.album || item?.albumName, "未知专辑"),
        artwork: displayText(item?.artwork || item?.coverImg || item?.picUrl || item?.cover),
        duration: normalizeDuration(item?.duration || item?.interval || item?.time),
        capabilities: {
            playback: capabilities.playback === true,
            download: capabilities.download === true,
            downloadViaPlayback: capabilities.downloadViaPlayback === true,
        },
        albumid: displayText(item?.albumid || item?.albumId),
        albummid: displayText(item?.albummid || item?.albumMid),
        raw,
    };
}

async function search(sourceId, keyword, page = 1, type = "music", options = {}) {
    const loaded = await loadPlugin(sourceId, options);

    if (typeof loaded.plugin.search !== "function") {
        throw new Error("该音源没有搜索接口");
    }

    const result = await withTimeout(
        loaded.plugin.search(String(keyword || "").trim(), Number(page) || 1, type || "music"),
        `音源 ${sourceId} 搜索`
    );
    return extractMusicItems(result)
        .slice(0, 100)
        .map((item) => normalizeMusicItem(loaded.source, item, loaded.capabilities));
}

async function getMetadata(sourceId, musicItem, options = {}) {
    const loaded = await loadPlugin(sourceId, options);
    const rawItem = musicItem?.raw || musicItem || {};
    const metadataMethod = loaded.plugin.getMusicInfo || loaded.plugin.getMusicDetail;

    if (typeof metadataMethod !== "function") {
        return {
            available: false,
            item: normalizeMusicItem(loaded.source, rawItem, loaded.capabilities),
            metadata: {},
        };
    }

    const result = await withTimeout(
        metadataMethod.call(loaded.plugin, rawItem),
        `音源 ${sourceId} 元数据请求`
    );
    const metadata = serializable(result) || {};
    const metadataBody = metadata?.data && typeof metadata.data === "object"
        ? metadata.data
        : metadata;
    const enrichedItem = {
        ...rawItem,
        ...(metadataBody && typeof metadataBody === "object" ? metadataBody : {}),
    };
    return {
        available: true,
        item: normalizeMusicItem(loaded.source, enrichedItem, loaded.capabilities),
        metadata,
    };
}

async function getLyric(sourceId, musicItem, options = {}) {
    const loaded = await loadPlugin(sourceId, options);

    if (typeof loaded.plugin.getLyric !== "function") {
        return { available: false, rawLrc: "", translation: "", raw: {} };
    }

    const rawItem = musicItem?.raw || musicItem || {};
    const result = await withTimeout(
        loaded.plugin.getLyric(rawItem),
        `音源 ${sourceId} 歌词请求`
    );
    const rawLrc =
        (typeof result === "string" ? result : null) ||
        result?.rawLrc ||
        result?.lrc ||
        result?.lyric ||
        result?.data?.lrc ||
        "";
    const translation = result?.translation || result?.translatedLrc || result?.tlyric || "";
    return {
        available: Boolean(String(rawLrc).trim()),
        rawLrc: String(rawLrc || ""),
        translation: String(translation || ""),
        raw: serializable(result) || {},
    };
}

async function resolvePlayback(sourceId, musicItem, options = {}) {
    const loaded = await loadPlugin(sourceId);
    if (!loaded.capabilities.playback) {
        throw new Error("该音源未启用播放能力");
    }

    const rawItem = musicItem?.raw || musicItem || {};
    const method = loaded.plugin.resolvePlayback || loaded.plugin.getMediaSource;
    const result = loaded.plugin.resolvePlayback
        ? await withTimeout(method.call(loaded.plugin, rawItem, options), `音源 ${sourceId} 播放解析`)
        : await withTimeout(method.call(loaded.plugin, rawItem, options.quality || "standard"), `音源 ${sourceId} 播放解析`);
    return normalizeResolvedResource(result, options.quality);
}

async function resolveDownload(sourceId, musicItem, options = {}) {
    const loaded = await loadPlugin(sourceId);
    if (!loaded.capabilities.download) {
        throw new Error("该音源未启用下载能力");
    }

    const rawItem = musicItem?.raw || musicItem || {};
    let method;
    let result;
    let viaPlayback = false;
    if (typeof loaded.plugin.resolveDownload === "function") {
        method = loaded.plugin.resolveDownload;
        result = await withTimeout(
            method.call(loaded.plugin, rawItem, options),
            `音源 ${sourceId} 下载解析`
        );
    } else if (typeof loaded.plugin.getDownloadSource === "function") {
        method = loaded.plugin.getDownloadSource;
        result = await withTimeout(
            method.call(loaded.plugin, rawItem, options.quality || "standard"),
            `音源 ${sourceId} 下载解析`
        );
    } else if (loaded.capabilities.downloadViaPlayback && typeof loaded.plugin.resolvePlayback === "function") {
        viaPlayback = true;
        method = loaded.plugin.resolvePlayback;
        result = await withTimeout(
            method.call(loaded.plugin, rawItem, options),
            `音源 ${sourceId} 下载回退解析`
        );
    } else if (loaded.capabilities.downloadViaPlayback && typeof loaded.plugin.getMediaSource === "function") {
        viaPlayback = true;
        method = loaded.plugin.getMediaSource;
        result = await withTimeout(
            method.call(loaded.plugin, rawItem, options.quality || "standard"),
            `音源 ${sourceId} 下载回退解析`
        );
    } else {
        throw new Error("该音源没有可用的下载解析接口");
    }
    return {
        ...normalizeResolvedResource(result, options.quality),
        viaPlayback,
    };
}

function listSources() {
    return readRegistry().map((source) => {
        let fileExists = false;
        let scanError = "";
        let requiredModules = [];
        let detectedPlayback = false;
        let detectedDownload = false;

        try {
            const filePath = resolveSourceFile(source);
            fileExists = true;
            const scan = staticScanSource(filePath);
            requiredModules = scan.requiredModules;
            if (path.extname(filePath).toLowerCase() === ".json") {
                const descriptor = JSON.parse(scan.code);
                detectedPlayback = Boolean(descriptor?.url);
                detectedDownload = Boolean(descriptor?.url);
            } else {
                detectedPlayback = /\b(?:resolvePlayback|getMediaSource)\b/.test(scan.code);
                detectedDownload = /\b(?:resolveDownload|getDownloadSource)\b/.test(scan.code);
            }
        } catch (error) {
            scanError = error.message;
        }

        const cached = pluginCache.get(source.id);
        const declared = source?.capabilities || {};
        const allowed = isContentPolicyAllowed(source);
        const detectedDownloadViaPlayback =
            allowed &&
            source?.userInstalled === true &&
            declared.downloadViaPlayback === true &&
            detectedPlayback &&
            !detectedDownload;
        return {
            ...serializable(source),
            capabilities: {
                search: Boolean(source?.capabilities?.search),
                metadata: Boolean(source?.capabilities?.metadata),
                lyrics: Boolean(declared.lyrics ?? declared.lyric),
                playback:
                    cached?.capabilities?.playback === true ||
                    (allowed && declared.playback === true && detectedPlayback),
                download:
                    cached?.capabilities?.download === true ||
                    (allowed && declared.download === true && (detectedDownload || detectedDownloadViaPlayback)),
                downloadViaPlayback:
                    cached?.capabilities?.downloadViaPlayback === true ||
                    detectedDownloadViaPlayback,
            },
            fileExists,
            scanError,
            requiredModules,
            loaded: pluginCache.has(source.id),
        };
    });
}

redirectConsoleToStderr();

module.exports = {
    REQUEST_TIMEOUT_MS,
    getLyric,
    getMetadata,
    listSources,
    loadPlugin,
    log,
    normalizeResolvedResource,
    resolveDownload,
    resolvePlayback,
    search,
    serializable,
    terminateProcess,
    unloadAllSources,
    unloadSource,
    withTimeout,
};
