module.exports = {
            search: async (keyword) => [{ id: `independent-${keyword}`, title: `Independent ${keyword}`, artist: "Fixture", album: "Tests", duration: 150 }],
            resolvePlayback: async () => ({ url: "http://127.0.0.1/fallback.wav" }),
            resolveDownload: async () => ({ url: "http://127.0.0.1/independent.flac", filename: "independent.flac" })
        };
