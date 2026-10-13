"""Génère les esquisses statiques (premier écran, 1440 x 900) des directions visuelles.
Même coque et mêmes données pour chaque monde ; seuls changent type, palette, densité et signature.
Usage : python3 gen.py  (écrit decision/<id>.html)
"""
# ruff: noqa: E501, RUF001, S311
# Esquisses jetables : longues chaînes HTML/CSS, typographie française, aléa non cryptographique.

import random
from pathlib import Path

OUT = Path(__file__).parent / "decision"
W, H, STEP, CW = 780, 520, 26, 14


def candles():
    rnd = random.Random(7)
    y, out = 300.0, []
    drift = [-2] * 9 + [-13] * 11 + [9] * 4 + [-6] * 6
    for i, d in enumerate(drift):
        o = y
        c = max(60, min(400, o + d + rnd.uniform(-14, 14)))
        hi, lo = min(o, c) - rnd.uniform(3, 14), max(o, c) + rnd.uniform(3, 14)
        x = 14 + i * STEP
        cls = "u" if c < o else "d"
        top, hgt = min(o, c), max(2, abs(c - o))
        out.append(
            f'<path class="{cls}" d="M{x + CW / 2} {hi:.0f}V{lo:.0f}M{x} {top:.0f}h{CW}v{hgt:.0f}h-{CW}z"/>'
        )
        y = c
    return "\n".join(out)


BASE_CSS = """
*{box-sizing:border-box;margin:0}
body{width:1440px;height:900px;overflow:hidden;background:var(--bg);color:var(--ink);font:14px/1.4 var(--font);font-variant-numeric:tabular-nums}
button{font:inherit;color:inherit;background:var(--panel2);border:1px solid var(--line);border-radius:var(--r);padding:7px 14px}
.sp{flex:1}.mute{color:var(--mute)}.gain{color:var(--gain)}.loss{color:var(--loss)}.blue{color:var(--blue)}
.top{height:48px;display:flex;align-items:center;gap:26px;padding:0 20px;background:var(--shell);border-bottom:1px solid var(--line)}
.logo{font:var(--logo);letter-spacing:var(--track)}
.top nav{display:flex;gap:22px}.top nav span{color:var(--mute);padding:14px 0}.top nav .on{color:var(--ink);box-shadow:0 2px 0 var(--blue)}
.kill{background:transparent;border-color:var(--loss);color:var(--loss)}
.inst{height:64px;display:flex;align-items:center;gap:16px;padding:0 20px}
.inst h1{font:var(--h1);letter-spacing:var(--track)}
.mode{background:var(--mode);color:var(--mode-ink);border-radius:var(--r);padding:3px 10px;font-weight:600}
.tabs{height:44px;display:flex;align-items:stretch;gap:4px;padding:0 20px;border-bottom:1px solid var(--line)}
.tabs span{display:flex;align-items:center;gap:10px;padding:0 16px;border-radius:var(--r) var(--r) 0 0;color:var(--mute)}
.tabs .on{background:var(--panel);color:var(--ink);box-shadow:inset 0 2px 0 var(--blue)}
.stats{height:104px;display:grid;grid-template-columns:2.4fr repeat(6,1fr);gap:1px;background:var(--line);border-bottom:1px solid var(--line)}
.stats div{background:var(--bg);padding:16px 20px;display:flex;flex-direction:column;justify-content:center;gap:4px}
.stats small{color:var(--mute);font-size:13px}.stats b{font:var(--num)}
.stats .solde b{font:var(--bignum);letter-spacing:var(--track)}
.solde p{display:flex;gap:18px;font-weight:600}
main{height:640px;display:grid;grid-template-columns:230px 1fr 330px}
aside,.chart{padding:16px 20px}
.left{border-right:1px solid var(--line);display:flex;flex-direction:column;gap:14px}
.left h2,.log h2{font:var(--h2);color:var(--mute)}
.card{background:var(--panel);border-radius:var(--r);padding:12px 14px;display:flex;flex-direction:column;gap:6px}
.pill{display:inline-block;font-style:normal;border:1px solid var(--line);border-radius:var(--r);padding:1px 8px;margin-right:4px}
.pill.on{border-color:var(--blue);color:var(--blue)}
.tf{display:flex;gap:6px;align-items:center;margin-bottom:10px}
.tf span{padding:4px 12px;border-radius:var(--r);color:var(--mute);border:1px solid transparent}
.tf .traded{border-color:var(--blue);color:var(--blue)}.tf .on{background:var(--blue);color:var(--bg);font-weight:700}
svg{display:block;width:100%;height:560px}
.u{fill:var(--up);stroke:var(--up);stroke-width:1.5}.d{fill:var(--down);stroke:var(--down);stroke-width:1.5}
.sl{stroke:var(--loss);stroke-dasharray:6 5;stroke-width:1.5}.tp{stroke:var(--gain);stroke-dasharray:6 5;stroke-width:1.5}
.path{stroke:var(--blue);stroke-width:2.5;fill:none}.mk{fill:var(--blue)}
svg text{font:600 13px var(--numfont);fill:var(--ink)}
.log{border-left:1px solid var(--line);display:flex;flex-direction:column;gap:10px}
.row{display:grid;grid-template-columns:52px 1fr auto;gap:10px;padding:9px 0;border-bottom:1px solid var(--line);font-family:var(--numfont)}
.row.new{background:var(--panel);margin:0 -12px;padding:9px 12px;border-radius:var(--r);border:0}
"""

SHELL = """<!doctype html><html lang="fr"><meta charset="utf-8"><title>Centrade : {name}</title>
{fonts}
<style>:root{{{vars}}}{base}{extra}</style>
<body>
<header class="top"><b class="logo">Centrade</b><nav><span class="on">Instances</span><span>Bibliothèque</span><span>Journal</span><span>Avancé</span></nav>
<span class="sp"></span><span class="mute">Bots 3 sur 3 joignables, observé il y a 2 s</span><button class="kill">Arrêt d'urgence</button></header>
<section class="inst"><span class="mute">Instances /</span><h1>Swing majors</h1><span class="mode">Mode test, chiffres simulés</span>
<span class="gain">● Actif</span><span class="mute">depuis 3 j 4 h 12 min · version 4</span><span class="sp"></span>
<button>Mettre en pause les achats</button><button>Arrêter</button></section>
<nav class="tabs"><span>Tout <b class="gain">+10,00 %</b></span><span class="on">BTC/USDT <b class="gain">+4,10 %</b></span><span>ETH/USDT <b class="loss">−0,80 %</b></span>
<span>SOL/USDT <b class="gain">+2,20 %</b></span><span>ADA/USDT <b class="mute">0,00 %</b></span></nav>
<section class="stats">
<div class="solde"><small>Solde de l'instance</small><b>2 000,00 USDT</b><p><span class="gain">▲ +7,91 % encaissé</span><span class="blue float">▲ +2,09 % en cours</span></p></div>
<div><small>Départ</small><b>1 818,18</b></div><div><small>Transactions</small><b>42</b></div><div><small>Réussites</small><b class="gain">27</b></div>
<div><small>Échecs</small><b class="loss">15</b></div><div><small>Taux de réussite</small><b>64 %</b></div><div><small>Plus forte baisse</small><b class="loss">−3,20 %</b></div>
</section>
<main>
<aside class="left"><h2>Compte</h2><div class="card"><b>Binance, compte test</b><span class="mute">Aucune clé transmise</span></div>
{left}
<h2>Automatisations</h2><div class="card"><b>Pause si perte du jour &gt; 3 %</b><span class="mute">Règle de protection</span></div></aside>
<section class="chart"><div class="tf"><span>5 min</span><span>15 min</span><span class="on traded">1 h</span><span>4 h</span><span>1 j</span><span class="sp"></span><span class="mute">Prix observé il y a 2 s</span></div>
<svg viewBox="0 0 {w} {h}">{defs}
{zone}
<path class="tp" d="M248 150H{w}"/><path class="sl" d="M248 372H540"/>
{candles}
<path class="path" d="M255 318L300 300L350 262L400 240L450 205L500 180L533 168"/>
<circle class="mk" cx="255" cy="318" r="7"/><circle class="mk" cx="533" cy="168" r="7"/>
<text x="232" y="346">Achat</text><text x="545" y="186">Vente</text>
{label}
{open}
<text x="{w}" y="140" text-anchor="end">Vente à gain (take-profit)</text><text x="548" y="390">Vente à perte (stop-loss)</text>
</svg></section>
<aside class="log"><h2>Journal des transactions</h2>
<div class="row"><span class="mute">09:14</span><span>Achat BTC/USDT</span><span class="blue">61 204,00</span></div>
<div class="row"><span class="mute">11:02</span><span>Vente ETH/USDT, stop</span><span class="loss">−12,40</span></div>
<div class="row"><span class="mute">13:48</span><span>Vente BTC/USDT, objectif</span><span class="gain">+41,06</span></div>
<div class="row"><span class="mute">14:05</span><span>Achat SOL/USDT</span><span class="blue">148,20</span></div>
<div class="row"><span class="mute">15:31</span><span>Achat refusé, protection</span><span class="mute">ADA/USDT</span></div>
<div class="row"><span class="mute">16:20</span><span>Vente SOL/USDT, signal</span><span class="gain">+9,85</span></div>
<div class="row new"><span class="mute">17:42</span><span>Achat BTC/USDT</span><span class="blue">62 880,00</span></div>
<span class="mute">Heure de Toronto. Les nouvelles lignes arrivent par le bas.</span></aside>
</main>"""

ZONE = '<rect x="255" y="168" width="278" height="150" fill="var(--gain)" opacity=".16" rx="{rx}"/>'
OPEN = (
    '<path class="sl" d="M650 300H{w}"/><circle class="mk" cx="650" cy="236" r="7"/>'
    '<path class="path" d="M650 236L690 250L730 222L766 214"/><text class="float" x="640" y="200" fill="var(--blue)">En cours +1,30 %</text>'
)

WORLDS = {
    "assigned": dict(
        name="Carte marine",
        fonts='<link href="https://fonts.googleapis.com/css2?family=Archivo:ital,wdth,wght@0,62..125,400..800;1,62..125,400..800&display=swap" rel="stylesheet">',
        vars="--bg:#0b1d2b;--shell:#0f3144;--panel:#12303f;--panel2:#173b4d;--line:#22495c;--ink:#ece6d3;--mute:#8fa9b3;"
        "--gain:#4ccb8f;--loss:#f0604a;--blue:#6fb6ff;--up:#4ccb8f;--down:#f0604a;--mode:#e6c867;--mode-ink:#2b2204;--r:3px;"
        "--font:'Archivo',sans-serif;--numfont:'Archivo',sans-serif;--logo:800 18px 'Archivo';--track:-.01em;"
        "--h1:700 24px 'Archivo';--h2:600 13px 'Archivo';--num:600 24px 'Archivo';--bignum:700 38px 'Archivo'",
        extra="body{font-stretch:92%}.stats b,.row,svg text{font-stretch:80%}.float{font-style:italic}"
        ".tabs .on{background:var(--shell)}",
        defs="",
        zone=ZONE.format(rx=0),
        label='<path d="M394 150v-34" stroke="var(--gain)"/><rect x="322" y="78" width="146" height="38" fill="var(--bg)" stroke="var(--gain)"/>'
        '<text x="395" y="103" text-anchor="middle" fill="var(--gain)">+3,20 % · +41,06 USDT</text>',
        # signature : le haut-fond, des courbes de niveau qui se resserrent vers la vente à perte
        open='<rect x="650" y="236" width="130" height="64" fill="#2f8fa3" opacity=".14"/><rect x="650" y="262" width="130" height="38" fill="#2f8fa3" opacity=".2"/>'
        '<rect x="650" y="284" width="130" height="16" fill="#2f8fa3" opacity=".3"/><path d="M650 262H780M650 284H780" stroke="#2f8fa3" stroke-width="1"/>'
        + OPEN,
    ),
    "model-pick": dict(
        name="Encre et indigo",
        fonts='<link href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700&family=Zen+Old+Mincho:wght@600;900&display=swap" rel="stylesheet">',
        vars="--bg:#14173a;--shell:#1b1f4d;--panel:#1e2252;--panel2:#262b63;--line:#313774;--ink:#f3eee2;--mute:#a3a6cf;"
        "--gain:#9ccf6b;--loss:#f0553a;--blue:#7cc4f0;--up:#f3eee2;--down:#f0553a;--mode:#f3eee2;--mode-ink:#14173a;--r:2px;"
        "--font:'Zen Kaku Gothic New',sans-serif;--numfont:'Zen Kaku Gothic New',sans-serif;--logo:900 20px 'Zen Old Mincho';--track:.01em;"
        "--h1:900 26px 'Zen Old Mincho';--h2:500 13px 'Zen Kaku Gothic New';--num:600 26px 'Zen Old Mincho';--bignum:900 40px 'Zen Old Mincho'",
        extra=".u{fill:none}",
        defs="",
        zone=ZONE.format(rx=0),
        # signature : le sceau, chaque trade terminé est tamponné de son résultat
        label='<g transform="rotate(-5 395 96)"><rect x="345" y="52" width="100" height="88" fill="var(--gain)"/>'
        '<text x="395" y="92" text-anchor="middle" style="font:900 24px \'Zen Old Mincho\';fill:#14173a">+3,20 %</text>'
        '<text x="395" y="120" text-anchor="middle" style="fill:#14173a">+41,06 USDT</text></g>',
        open=OPEN,
    ),
    "challenger-lobes": dict(
        name="Aplats et capsules",
        fonts='<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500&display=swap" rel="stylesheet">',
        vars="--bg:#f5f1e4;--shell:#8ed462;--panel:#ffffff;--panel2:#ffffff;--line:#d9d3bf;--ink:#2c2e2a;--mute:#6d6f66;"
        "--gain:#2f8f1f;--loss:#d8402c;--blue:#1479d6;--up:#5cbf3a;--down:#ff705d;--mode:#f5e211;--mode-ink:#2c2e2a;--r:999px;"
        "--font:'Bricolage Grotesque',sans-serif;--numfont:'Bricolage Grotesque',sans-serif;--logo:500 22px 'Bricolage Grotesque';--track:-.05em;"
        "--h1:500 30px 'Bricolage Grotesque';--h2:500 13px 'Bricolage Grotesque';--num:500 26px 'Bricolage Grotesque';--bignum:500 44px/1 'Bricolage Grotesque'",
        extra=".card{border-radius:22px}.row.new{border-radius:22px}.top{border:0}.top nav span{color:#2c2e2a}.top .mute{color:#2c2e2a}"
        ".kill{background:#ff705d;color:#2c2e2a;border:0}.stats{gap:0;background:var(--bg)}.stats div{background:none}"
        ".tabs .on{box-shadow:none;border-radius:999px;background:#2c2e2a;color:#f5f1e4;margin:6px 0}.tabs .on b{color:#8ed462}",
        defs="",
        # signature : la zone du trade est un lobe d'aplat, sans contour
        zone='<path d="M240 318C230 250 330 150 430 150S560 120 548 190 470 330 380 336 250 372 240 318z" fill="#8ed462" opacity=".55"/>',
        label='<rect x="318" y="60" width="154" height="44" rx="22" fill="#2c2e2a"/><circle cx="450" cy="82" r="14" fill="#8ed462"/>'
        '<text x="332" y="87" style="fill:#f5f1e4">+3,20 % · +41,06</text>',
        open=OPEN,
    ),
    "canon": dict(
        name="Standard des plateformes d'échange",
        fonts='<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;800&family=Figtree:wght@400;600&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">',
        vars="--bg:#0b0e13;--shell:#0b0e13;--panel:#12161d;--panel2:#171c25;--line:#222834;--ink:#e9e7e1;--mute:#8a909c;"
        "--gain:#2ebd85;--loss:#f6465d;--blue:#4c8dff;--up:#2ebd85;--down:#f6465d;--mode:transparent;--mode-ink:#f0b429;--r:2px;"
        "--font:'Figtree',sans-serif;--numfont:'JetBrains Mono',monospace;--logo:800 22px 'Barlow Condensed';--track:.01em;"
        "--h1:800 30px 'Barlow Condensed';--h2:600 13px 'Figtree';--num:600 22px 'JetBrains Mono';--bignum:600 34px 'JetBrains Mono'",
        extra=".mode{border:1px dashed #f0b429}.logo,.inst h1{text-transform:uppercase}",
        defs='<pattern id="h" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><path d="M0 0V10" stroke="#2ebd85" stroke-width="4" opacity=".28"/></pattern>',
        zone='<rect x="255" y="168" width="278" height="150" fill="url(#h)"/>',
        label='<path d="M394 150v-34" stroke="var(--gain)"/><rect x="316" y="80" width="158" height="36" fill="#12161d" stroke="var(--gain)"/>'
        '<text x="395" y="103" text-anchor="middle" fill="var(--gain)">+3,20 % · +41,06</text>',
        open=OPEN,
    ),
}

LEFT = """<h2>Stratégies</h2><div class="card"><b>Croisement de moyennes</b><span><i class="pill on">BTC/USDT</i><i class="pill">ETH/USDT</i></span><span class="mute">Unité de temps 1 h</span></div>
<div class="card"><b>Retour à la moyenne</b><span><i class="pill">SOL/USDT</i><i class="pill">ADA/USDT</i></span><span class="mute">Unité de temps 15 min</span></div>
"""

HATCH = (
    '<pattern id="h" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate({a})">'
    '<path d="M0 0V5" stroke="{c}" stroke-width="{sw}" opacity="{o}"/></pattern>'
)
# Plan de réseau : chaque paire est une ligne, chaque stratégie une correspondance
TRANSIT_LEFT = """<h2>Paires et stratégies</h2><svg viewBox="0 0 225 250" style="height:250px">
<g fill="none" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">
<path stroke="#ffb53a" d="M14 24H60L84 60H120"/><path stroke="#b98cff" d="M14 96H60L84 66H120"/>
<path stroke="#2ad1c9" d="M14 150H60L84 180H120"/><path stroke="#ff86c8" d="M14 222H60L84 186H120"/>
<path stroke="#f4f1e8" stroke-width="3" d="M120 63V183"/></g>
<g fill="#0d1633" stroke="#f4f1e8" stroke-width="3"><circle cx="120" cy="63" r="9"/><circle cx="120" cy="183" r="9"/></g>
<g style="font:600 12px Overpass;fill:#f4f1e8"><text x="14" y="14">BTC/USDT</text><text x="14" y="116">ETH/USDT</text>
<text x="14" y="140">SOL/USDT</text><text x="14" y="242">ADA/USDT</text>
<text x="136" y="58">Croisement</text><text x="136" y="74" style="fill:#9aa6cf">1 h</text>
<text x="136" y="178">Retour</text><text x="136" y="194" style="fill:#9aa6cf">15 min</text></g></svg>
"""
FORM = ",".join(
    f"{c} {i * 10}% {i * 10 + 8}%,transparent {i * 10 + 8}% {i * 10 + 10}%"
    for i, c in enumerate(
        [
            "var(--gain)",
            "var(--gain)",
            "var(--loss)",
            "var(--gain)",
            "var(--gain)",
            "var(--gain)",
            "var(--loss)",
            "var(--loss)",
            "var(--gain)",
            "var(--blue)",
        ]
    )
)
ROUND2 = {
    "r1-assigned": dict(
        name="Billet et gravure",
        fonts='<link href="https://fonts.googleapis.com/css2?family=Albert+Sans:wght@400;600;700&family=Bodoni+Moda:opsz,wght@6..96,600;6..96,800&display=swap" rel="stylesheet">',
        vars="--bg:#17141d;--shell:#3a2a78;--panel:#1f1b28;--panel2:#272233;--line:#352f45;--ink:#f1ead9;--mute:#a59fb5;"
        "--gain:#58c48a;--loss:#ef5d4f;--blue:#62a8ff;--up:#58c48a;--down:#ef5d4f;--mode:#8f74e8;--mode-ink:#14101f;--r:2px;"
        "--font:'Albert Sans',sans-serif;--numfont:'Albert Sans',sans-serif;--logo:800 21px 'Bodoni Moda';--track:.02em;"
        "--h1:800 27px 'Bodoni Moda';--h2:600 13px 'Albert Sans';--num:600 27px 'Bodoni Moda';--bignum:800 44px/1 'Bodoni Moda'",
        extra=".top{border-bottom:3px double #8f74e8}.top nav span,.top .mute{color:#d9d2f2}.stats{border-bottom:3px double var(--line)}",
        defs=HATCH.format(a=35, c="#58c48a", sw=1.2, o=".7"),
        # signature : la taille-douce, des hachures fines de billet remplissent la zone d'un trade
        zone='<rect x="255" y="168" width="278" height="150" fill="url(#h)"/><rect x="255" y="168" width="278" height="150" fill="none" stroke="#58c48a" stroke-width="1"/>',
        label='<path d="M394 150v-30" stroke="var(--gain)"/><rect x="314" y="62" width="160" height="58" fill="#17141d" stroke="#58c48a"/>'
        '<rect x="318" y="66" width="152" height="50" fill="none" stroke="#58c48a" stroke-width=".6"/>'
        '<text x="394" y="92" text-anchor="middle" style="font:800 22px \'Bodoni Moda\';fill:#58c48a">+3,20 %</text>'
        '<text x="394" y="109" text-anchor="middle" style="font-size:11px;fill:#f1ead9">+41,06 USDT</text>',
        open=OPEN,
        left=LEFT,
    ),
    "r1-pick": dict(
        name="Chronométrage",
        fonts='<link href="https://fonts.googleapis.com/css2?family=Saira:ital,wght@0,400;0,600;1,800&family=Saira+Semi+Condensed:wght@500;700&display=swap" rel="stylesheet">',
        vars="--bg:#101114;--shell:#17181d;--panel:#1b1d23;--panel2:#22252d;--line:#2c2f39;--ink:#f4f4f0;--mute:#9a9ea9;"
        "--gain:#3ddc84;--loss:#ff4d4d;--blue:#3aa0ff;--up:#3ddc84;--down:#ff4d4d;--mode:#ffd60a;--mode-ink:#101114;--r:3px;"
        "--font:'Saira',sans-serif;--numfont:'Saira Semi Condensed',sans-serif;--logo:italic 800 21px 'Saira';--track:0;"
        "--h1:italic 800 27px 'Saira';--h2:600 13px 'Saira';--num:700 27px 'Saira Semi Condensed';--bignum:700 42px/1 'Saira Semi Condensed'",
        # signature : la bande de forme, les dix derniers trades en segments de couleur
        extra=".mode{transform:skewX(-10deg)}.solde::after{content:'';height:9px;width:330px;background:linear-gradient(90deg,"
        + FORM
        + ")}"
        ".solde{gap:3px!important}.tabs .on{box-shadow:inset 0 3px 0 var(--mode)}",
        defs="",
        zone=ZONE.format(rx=0),
        label='<path d="M394 150v-30" stroke="var(--gain)"/><path d="M326 84h150l-10 36h-150z" fill="#3ddc84"/>'
        '<text x="396" y="108" text-anchor="middle" style="font:700 15px \'Saira Semi Condensed\';fill:#101114">+3,20 % · +41,06 USDT</text>',
        open=OPEN,
        left=LEFT,
    ),
    "r1-transit": dict(
        name="Plan de réseau",
        fonts='<link href="https://fonts.googleapis.com/css2?family=Overpass:wght@400;600;800&display=swap" rel="stylesheet">',
        vars="--bg:#0d1633;--shell:#111d44;--panel:#142252;--panel2:#1a2a62;--line:#26356e;--ink:#f4f1e8;--mute:#9aa6cf;"
        "--gain:#37c871;--loss:#ff5a4f;--blue:#5db1ff;--up:#37c871;--down:#ff5a4f;--mode:#f4f1e8;--mode-ink:#0d1633;--r:999px;"
        "--font:'Overpass',sans-serif;--numfont:'Overpass',sans-serif;--logo:800 20px 'Overpass';--track:0;"
        "--h1:800 26px 'Overpass';--h2:600 13px 'Overpass';--num:600 26px 'Overpass';--bignum:800 42px/1 'Overpass'",
        extra=".card{border-radius:10px}.tabs span::before{content:'';width:18px;height:5px;border-radius:3px;background:#ffb53a}"
        ".tabs span:nth-child(1)::before{background:#f4f1e8}.tabs span:nth-child(3)::before{background:#b98cff}"
        ".tabs span:nth-child(4)::before{background:#2ad1c9}.tabs span:nth-child(5)::before{background:#ff86c8}"
        ".tabs .on{box-shadow:inset 0 3px 0 #ffb53a;border-radius:10px 10px 0 0}.row.new{border-radius:10px}",
        defs="",
        zone=ZONE.format(rx=10),
        label='<path d="M394 150v-30" stroke="var(--gain)"/><rect x="318" y="84" width="152" height="36" rx="18" fill="#0d1633" stroke="#37c871" stroke-width="3"/>'
        '<text x="394" y="107" text-anchor="middle" fill="#37c871">+3,20 % · +41,06 USDT</text>',
        open=OPEN,
        left=TRANSIT_LEFT,
    ),
}
if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    c = candles()
    for wid, w in {**WORLDS, **ROUND2}.items():
        w.setdefault("left", LEFT)
        html = SHELL.format(
            base=BASE_CSS,
            candles=c,
            w=W,
            h=H,
            **{k: v.replace("{w}", str(W)) for k, v in w.items()},
        )
        (OUT / f"{wid}.html").write_text(html, encoding="utf-8")
        print(wid, len(html.splitlines()), "lignes")
