"""Gera feed.json para o destaque da Clara TV.

Em alta no TMDB (filmes e séries) -> só o que está por assinatura no Brasil nos apps da TV ->
sinopse em pt-BR, fundo sem texto, logo do título -> nota do IMDb (datasets oficiais, title.ratings).

uso: TMDB_TOKEN=... python3 build_feed.py [saida.json]
"""
import csv, gzip, io, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

TOKEN = os.environ["TMDB_TOKEN"].strip()
API = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/"
RATINGS = "https://datasets.imdbws.com/title.ratings.tsv.gz"
MAX_ITEMS = 20
PAGES = 5

# provider_id do TMDB (região BR) -> app da TV. Ordem = preferência quando o título está em mais de um.
APPS = [
    ({8}, "Netflix", "com.netflix.ninja"),
    ({1899, 384}, "HBO Max", "com.hbo.hbonow"),
    ({337}, "Disney+", "com.disney.disneyplus"),
    ({350}, "Apple TV", "com.apple.atve.amazon.appletv"),
]


def get(path, **params):
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(2 + attempt * 2)
                continue
            raise
    raise RuntimeError(f"TMDB não respondeu: {path}")


def pick_app(providers):
    flat = {p["provider_id"] for p in providers.get("results", {}).get("BR", {}).get("flatrate", [])}
    for ids, name, pkg in APPS:
        if ids & flat:
            return name, pkg
    return None


def best(images, langs):
    """Imagem mais votada entre as línguas pedidas, na ordem de preferência."""
    for lang in langs:
        pool = [i for i in images if i.get("iso_639_1") == lang]
        if pool:
            return max(pool, key=lambda i: (i.get("vote_average", 0), i.get("width", 0)))["file_path"]
    return None


def imdb_ratings(wanted):
    """{tt...: (nota, votos)} só para os ids pedidos, lendo o dataset em streaming."""
    out = {}
    with urllib.request.urlopen(RATINGS, timeout=120) as r:
        rows = csv.reader(io.TextIOWrapper(gzip.GzipFile(fileobj=r), encoding="utf-8"), delimiter="\t")
        next(rows)
        for tconst, avg, votes in rows:
            if tconst in wanted:
                out[tconst] = (float(avg), int(votes))
    return out


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "feed.json"
    seen, picked = set(), []
    for page in range(1, PAGES + 1):
        for t in get("/trending/all/week", language="pt-BR", page=page)["results"]:
            kind = t.get("media_type")
            if kind not in ("movie", "tv") or (kind, t["id"]) in seen:
                continue
            seen.add((kind, t["id"]))
            d = get(f"/{kind}/{t['id']}", language="pt-BR",
                    append_to_response="watch/providers,external_ids,images",
                    include_image_language="pt,en,null")
            app = pick_app(d.get("watch/providers", {}))
            overview = (d.get("overview") or "").strip()
            imgs = d.get("images", {})
            backdrop = best(imgs.get("backdrops", []), [None, "en", "pt"]) or d.get("backdrop_path")
            if not app or not overview or not backdrop:
                continue
            date = d.get("release_date") or d.get("first_air_date") or ""
            logo = best(imgs.get("logos", []), ["pt", "en"])
            picked.append({
                "id": f"{kind}-{d['id']}",
                "type": "Filme" if kind == "movie" else "Série",
                "title": d.get("title") or d.get("name"),
                "year": date[:4],
                "overview": overview,
                "genres": [g["name"] for g in d.get("genres", [])][:2],
                "backdrop": IMG + "w1280" + backdrop,
                "logo": IMG + "w500" + logo if logo else None,
                "imdb_id": (d.get("external_ids") or {}).get("imdb_id"),
                "app": app[0],
                "package": app[1],
            })
            if len(picked) >= MAX_ITEMS:
                break
        if len(picked) >= MAX_ITEMS:
            break

    ratings = imdb_ratings({p["imdb_id"] for p in picked if p["imdb_id"]})
    for p in picked:
        avg, votes = ratings.get(p.pop("imdb_id") or "", (None, 0))
        p["imdb"] = avg if votes >= 500 else None
        p["imdb_votes"] = votes

    feed = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "credits": "Dados: TMDB · Nota: IMDb", "items": picked}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=1)
    print(f"{len(picked)} títulos -> {out_path}")
    for p in picked:
        print(f"  {p['app']:<9} {p['type']:<6} {p['imdb'] or '-':<4} {p['title']}")


if __name__ == "__main__":
    main()
