# clara-tv-feed

Sugestões de filmes e séries para o destaque da Clara TV (launcher do Fire Stick).

Todo dia às 06:00 (Brasília) o GitHub Actions roda `build_feed.py`: pega o que está em alta no
[TMDB](https://www.themoviedb.org/), mantém só o que está por assinatura no Brasil na Netflix,
HBO Max, Disney+ ou Apple TV, e junta a nota do IMDb (datasets públicos, `title.ratings`).
O resultado é publicado em `https://brennojahar.github.io/clara-tv-feed/feed.json`.

Precisa do secret `TMDB_TOKEN` (API Read Access Token do TMDB).

Este produto usa a API do TMDB, mas não é endossado nem certificado pelo TMDB.
Notas do IMDb: dados cedidos por IMDb (https://www.imdb.com), uso pessoal e não comercial.
