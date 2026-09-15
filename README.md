# NOCLIP Pen Studio

Farvekonfigurator til **Chili Concept BND188AL NOCLIP** — aluminiumskuglepen uden clip.
Vælg penfarve, overflade, metaldele og logo, se resultatet med det samme, og hent et
færdigt produktbillede i fuld opløsning.

Bygget til Metz A/S. Ingen build, ingen afhængigheder i browseren — én HTML-fil og
seks PNG-lag.

---

## Hvad den gør

Værktøjet **tegner ikke pennen om**. Det skiller to rigtige produktfotos ad i lag og
udskifter kun farven. Lysets struktur, gummiglansen, det børstede metal og kanterne
kommer fra fotoet, så resultatet er et retoucheret produktfoto — ikke en 3D-tegning.

* To positurer: lodret og diagonal, med samme farve- og logoindstillinger
* Lagerfarverne fra databladet, kalibreret mod fotos af faktiske Chili-penne
* Metaldele (Part 2) i sølv, krom, mørkegrå, sort, guld og rosaguld
* Logo-upload med automatisk beskæring af filens tomme kant
* Trykfelt-overlay i millimeter: zone 1 (50 × 6 mm) og all over 360° (106 × 29,83 mm)
* Eksport i 1600 px, transparent baggrund, tæt beskæring og 2× opskalering

### Sådan bruges det i praksis

1. Vælg kundens farve — enten en lagerfarve eller deres egen kode i hex-feltet
2. Træk kundens logofil ind på billedet
3. Klik **Fyld zone 1 helt ud**, eller sæt højden selv
4. Tjek den grønne prik under skyderne: den siger om trykket kan være i zone 1
5. **Hent PNG**

> **Vigtigt:** billederne er salgsmockups. Endelig trykfarve skal altid godkendes mod
> Pantone-vifte, før der sendes bestilling til leverandøren.

---

## Deploy til Vercel

Projektet er statisk. Ingen build, ingen miljøvariabler.

```bash
git clone https://github.com/<bruger>/noclip-pen-studio.git
cd noclip-pen-studio
npx vercel          # første gang: følg prompterne
npx vercel --prod   # udgiv
```

Eller via vercel.com: **Add New → Project → Import Git Repository**. Vercel læser
`vercel.json`, finder `public/` og serverer den som den er. Framework: **Other**.
Build Command og Install Command skal stå tomme.

### Lokalt

```bash
cd public && python3 -m http.server 8080
```

Åbn <http://localhost:8080>. Siden skal serveres over HTTP — åbner du `index.html`
direkte som fil, blokerer browseren læsning af lag-billederne.

---

## Hvordan lagene virker

Hvert foto er skilt ad i tre PNG-filer. Farverne i dem er ikke billeder man kigger
på — det er koefficienter:

| Fil | R | G | B |
|---|---|---|---|
| `pen_?1.png` | lakkoefficient (×200) | hvidt lys | dækning / alpha |
| `pen_?2.png` | skaft | stylus-top | metaldele |
| `pen_?3.png` | metalluminans | illumination | — |

Renderingen er så: `farve = lak × dinFarve + hvidtLys`, metaldelene slås op i en
gradient, og det hele lægges på baggrunden med dækningen som alpha. Det kører i en
`<canvas>` i browseren, cirka 15 ms pr. billede.

Lagene er beskåret til pennens omrids, fordi resten af billedfladen er tom
baggrund. Det gør filerne omkring 15 gange mindre og renderingen tilsvarende
hurtigere.

### Hvorfor tallene er målte og ikke skønnede

Alt der kunne måles, er målt mod rigtige fotos:

| Indstilling | Grundlag |
|---|---|
| Sort #262726 | målt på VE1102 — nominel sort renderede 18 niveauer for mørkt |
| Navy 289C #1B3B59 | målt på ALK105 |
| Rød 485C #FF2F35 | målt på DAN1009 og PA354 |
| Sølv (Part 2) | rammer BCG-pennens metaldele inden for 4,3 niveauer |
| Mørkegrå (Part 2) | rammer ALK-pennens inden for 5,6 niveauer |
| Trykplacering | målt på et virkeligt tryk: 4,3 mm højt, 80 % oppe ad skaftet |
| Overflade "Gummi" | gengiver kildefotoet med 3,5 niveauers afvigelse |

**Blank** og **mat** er stadig skøn — alle referencefotos er gummi/soft-touch.
Det samme gælder guld og rosaguld på metaldelene. Dukker der en variant op i et
kundejob, kan de kalibreres på samme måde.

---

## Tilføj et produkt

Se [`tools/README.md`](tools/README.md). Kort fortalt: kør et produktfoto gennem
`tools/build_layers.py`, læg de tre PNG-filer i `public/`, og indsæt de tal scriptet
udskriver i `POSES` i `public/index.html`.

---

## Rettigheder

Koden i dette repo er MIT-licenseret — se [LICENSE](LICENSE).

**Lag-filerne i `public/` er afledt af Chili Concepts produktfotografier og er ikke
omfattet af MIT-licensen.** De ligger her efter aftale om brug i Metz' salgsarbejde.
Skal værktøjet bruges uden for den aftale, skal lagene bygges fra egne fotos med
`tools/build_layers.py`. Se [NOTICE](NOTICE).

Eksempel-logoet (`public/sample-logo.png`) er en neutral pladsholder. Kundelogoer
uploades af brugeren og forlader aldrig browseren — der er ingen server og ingen
lagring.
