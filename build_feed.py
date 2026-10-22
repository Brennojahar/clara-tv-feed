"""Gera feed.json para o destaque da Clara TV.

Em alta no TMDB (filmes e séries) -> só o que está por assinatura no Brasil nos apps da TV ->
sinopse e pôster em pt-BR, fundo sem texto, logo do título -> nota do IMDb (datasets oficiais, title.ratings).

uso: TMDB_TOKEN=... python3 build_feed.py [saida.json]
"""
import csv, gzip, io, json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

TOKEN = os.environ["TMDB_TOKEN"].strip()
API = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/"
RATINGS = "https://datasets.imdbws.com/title.ratings.tsv.gz"
MAX_ITEMS = 20
PAGES = 5

JUSTWATCH = "https://apis.justwatch.com/graphql"
SYNOPSIS_MAX = 170   # ~3 linhas no bloco da TV

# Nome do serviço no JustWatch para cada app (as variantes "Amazon Channel" abrem no Prime Video, não servem).
JW_NAMES = {"Netflix": ("Netflix",), "HBO Max": ("HBO Max", "Max"), "Disney+": ("Disney Plus",), "Apple TV": ("Apple TV", "Apple TV Plus")}

# provider_id do TMDB (região BR) -> app da TV. Ordem = preferência quando o título está em mais de um.
APPS = [
    ({8}, "Netflix", "com.netflix.ninja"),
    ({1899, 384}, "HBO Max", "com.hbo.hbonow"),
    ({337}, "Disney+", "com.disney.disneyplus"),
    ({350}, "Apple TV", "com.apple.atve.amazon.appletv"),
]


# Aceita as duas credenciais do TMDB: o "API Read Access Token" (JWT, vai no header) ou a "API Key" curta (query).
BEARER = TOKEN.count(".") == 2


def get(path, **params):
    if not BEARER:
        params["api_key"] = TOKEN
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    headers = {"Accept": "application/json"}
    if BEARER:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
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


def short_synopsis(text):
    """As primeiras frases que cabem em SYNOPSIS_MAX: a premissa, sem reticências nem spoiler do fim."""
    text = " ".join(text.split())
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    out = ""
    for sent in sentences:
        if len(out) + len(sent) + 1 > SYNOPSIS_MAX:
            break
        out = f"{out} {sent}".strip()
    if out:
        return out
    first = sentences[0]
    cut = max(first.rfind(", ", 0, SYNOPSIS_MAX), first.rfind("; ", 0, SYNOPSIS_MAX), first.rfind(" e ", 0, SYNOPSIS_MAX))
    if cut > SYNOPSIS_MAX * 0.5:
        return first[:cut].rstrip(" ,;") + "."
    return first[:first.rfind(" ", 0, SYNOPSIS_MAX - 1)].rstrip(" ,;") + "…"


def jw_query(query, variables):
    req = urllib.request.Request(JUSTWATCH, data=json.dumps({"query": query, "variables": variables}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "clara-tv-feed"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


JW_SEARCH = """query($q:String!){ popularTitles(country:BR, first:5, filter:{searchQuery:$q}) { edges { node {
  objectType content(country:BR, language:"pt") { externalIds { tmdbId } }
  offers(country:BR, platform:WEB) { monetizationType package { clearName } standardWebURL } } } } }"""


def clean_url(url):
    """Link que abre a página do título no app da TV (sem parâmetros de rastreio)."""
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qs(parts.query)
    if parts.netloc == "tv.apple.com" and "showId" in query:   # episódio -> página da série
        return f"https://tv.apple.com/br/show/s/{query['showId'][0]}"
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def deep_link(names, tmdb_id, kind, app):
    """Link do título dentro do app escolhido, via JustWatch; None quando não achar (a TV abre só o app)."""
    want = "MOVIE" if kind == "movie" else "SHOW"
    for name in dict.fromkeys(n for n in names if n):
        try:
            edges = jw_query(JW_SEARCH, {"q": name})["data"]["popularTitles"]["edges"]
        except Exception as e:
            print(f"  JustWatch falhou para {name}: {e}")
            return None
        for e in edges:
            n = e["node"]
            if n["objectType"] != want or str((n["content"]["externalIds"] or {}).get("tmdbId")) != str(tmdb_id):
                continue
            for o in n["offers"]:
                if o["monetizationType"] == "FLATRATE" and o["package"]["clearName"] in JW_NAMES[app] and o.get("standardWebURL"):
                    return clean_url(o["standardWebURL"])
            return None
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
            poster = best(imgs.get("posters", []), ["pt", "en"]) or d.get("poster_path")
            if not app or not overview or not poster:
                continue
            date = d.get("release_date") or d.get("first_air_date") or ""
            logo = best(imgs.get("logos", []), ["pt", "en"])
            picked.append({
                "id": f"{kind}-{d['id']}",
                "type": "Filme" if kind == "movie" else "Série",
                "title": d.get("title") or d.get("name"),
                "year": date[:4],
                "overview": short_synopsis(overview),
                "link": deep_link([d.get("title") or d.get("name"), d.get("original_title") or d.get("original_name")],
                                  d["id"], kind, app[0]),
                "genres": [g["name"] for g in d.get("genres", [])][:2],
                "poster": IMG + "w342" + poster,
                "backdrop": IMG + "w1280" + backdrop if backdrop else None,
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
        print(f"  {p['app']:<9} {p['type']:<6} {p['imdb'] or '-':<4} {p['title']}  {'link' if p['link'] else 'SEM LINK'}")


if __name__ == "__main__":
    main()
