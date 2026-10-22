# clara-tv-feed

Sugestões de filmes e séries para o destaque da Clara TV (launcher do Fire Stick).

Todo dia às 06:00 (Brasília) o GitHub Actions roda `build_feed.py`: pega o que está em alta no
[TMDB](https://www.themoviedb.org/), mantém só o que está por assinatura no Brasil na Netflix,
HBO Max, Disney+ ou Apple TV, e junta a nota do IMDb (datasets públicos, `title.ratings`).
O resultado é publicado em `https://brennojahar.github.io/clara-tv-feed/feed.json`.

Precisa do secret `TMDB_TOKEN` (API Read Access Token do TMDB).

Este produto usa a API do TMDB, mas não é endossado nem certificado pelo TMDB.
Notas do IMDb: dados cedidos por IMDb (https://www.imdb.com), uso pessoal e não comercial.

O link que abre cada título direto no app (Netflix, HBO Max, Disney+, Apple TV) vem da API
GraphQL pública do JustWatch, que não é oficialmente documentada; se ela mudar, a TV volta a abrir só o app.
A sinopse é cortada nas primeiras frases (a premissa), para caber sem reticências e sem spoiler.
