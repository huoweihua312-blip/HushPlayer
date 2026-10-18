module.exports = {
            search: async (keyword) => [{ id: `open-${keyword}`, title: `Open ${keyword}`, artist: "Fixture", album: "Tests", duration: 120 }],
            resolvePlayback: async (track) => {
                await new Promise((resolve) => setTimeout(resolve, Number(track.delay || 0)));
                if (track.fail) throw new Error("fixture failure");
                return { url: `http://127.0.0.1:8765/${track.id}.mp3`, headers: {} };
            }
        };
