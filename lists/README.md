# Lidarr genre starter lists

## Main custom list

https://raw.githubusercontent.com/T2112/lidarr-soulseek/main/lists/lidarr-custom-list.json

Curated popular / widely recorded artists across rock, pop, hip-hop, country, jazz, blues, metal, R&B/soul, electronic, folk, punk, indie, reggae, Latin, funk, classical, goth, emo, women artists, game soundtracks, electro-swing, and more.

**Current status (2026-09-26):** **976** unique MusicBrainz artist IDs resolved. Full list is maintained in the project workspace (`artifacts/lidarr-lists/`). GitHub raw may lag or be truncated due to size limits on large JSON pushes via the connector; treat the local file as authoritative when they differ. 0 names still pending after name normalization (Bart & Baker resolved as Bart&Baker, MBID 736fa8ab-d788-4690-8ec8-8bb286aa3061).

## Festival list (Woodstock + Qlimax + Ozzfest)

https://raw.githubusercontent.com/T2112/lidarr-soulseek/main/lists/festivals-woodstock-qlimax-ozzfest.json

Separate import list of musicians, DJs, and groups that played:
- Woodstock 1969, 1994, and 1999
- Qlimax (all official Dutch editions, 2000–2024)
- Ozzfest (US / UK / Europe / Japan editions, 1996–2018)

About 457 MusicBrainz artists after resolving official lineups. A handful of local openers and one-off aliases without a usable MusicBrainz page were skipped.

## Safer add settings

Lidarr → Settings → Import Lists → + → Custom List → paste either URL.

Recommended:
- Monitor: **Latest Album** (or First Album)
- Monitor new items: **New** or **None**
- Start search for missing albums: **off** until you have tagged the batch
- Add a tag such as `genre-starter` so you can delete the whole batch if needed

Lidarr skips artists already in your library. Adding hundreds of artists with "all albums + search" will queue more than a Soulseek worker can finish quickly.

Files in this folder / project:
- `lidarr-custom-list.json` / `artists.txt` / `artists-by-genre.txt`
- `festivals-woodstock-qlimax-ozzfest.json` / festival artists text
