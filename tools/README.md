# Tilføj et produkt eller en positur

`build_layers.py` skiller et produktfoto ad i de tre lag som værktøjet renderer fra.
Det er det eneste skridt der kræver Python; resten er at kopiere nogle tal ind.

## Installer

```bash
pip install -r requirements.txt
```

## Kravene til fotoet

Det er her det afgøres om resultatet bliver godt. I prioriteret rækkefølge:

**Så lidt komprimering som muligt.** Den vigtigste enkeltfaktor. Bed leverandøren om
filen som de sendte den — ikke en der er trukket ud af en PowerPoint eller et website.
Forskellen mellem en tabsfri og en hårdt komprimeret JPEG er forskellen mellem et
rent skaft og et plettet.

**Én pen, ren lys baggrund, hele pennen i billedet.** Ingen hånd, ingen rekvisitter,
ingen anden pen. Baggrunden må gerne have en svag skygge — den bliver klippet fra.

**En mættet mellemtone som grundfarve.** Rød, blå eller grøn. Sort og hvid har for
lille tonespredning til at bære en farveudskiftning: der er simpelthen ikke nok
information tilbage til at genskabe formen, og resultatet bliver en flad silhuet.
Man kan sagtens lave en sort variant ud af en blå base — den anden vej virker ikke.

**Blankt skaft hvis muligt.** Er der et tryk, så brug `--erase-logo`; det males væk,
men det er en fejlkilde mindre at slippe for.

**Skarpt fokus hele vejen ned ad skaftet**, og begge metaldele synlige.

## Kør

```bash
python build_layers.py ../fotos/ny_pen.jpg --tag vert2 --out ../public
```

Med et eksisterende tryk på skaftet:

```bash
python build_layers.py ../fotos/ny_pen.jpg --tag vert2 --out ../public --erase-logo
```

Scriptet skriver `vert2_l1.png`, `vert2_l2.png`, `vert2_l3.png` og `vert2_meta.json`,
og udskriver de tal du skal bruge.

## Sæt det ind i siden

Omdøb de tre PNG-filer til det mønster siden forventer — `pen_x1.png`, `pen_x2.png`,
`pen_x3.png` — og tilføj en post i `POSES` øverst i scriptet i `public/index.html`:

```js
const POSES={
  vert:{ ... },
  diag:{ ... },
  minNye:{
    axis:{cx:…, cy:…, dx:…, dy:…},      // fra meta.json: axis
    penT:[…,…], barrelT:[…,…],          // fra meta.json
    pxAlong:…, pxAcross:…,              // px pr. mm, langs og på tværs
    crop:[…,…,…,…],                     // fra meta.json: crop
    portrait:{x:…,y:…,w:…,h:…},         // den tætte ramme
    contact:[…,…],                      // hvor spidsen rører underlaget
    logoT:…, logoH:4.3, shadowGain:0.2,
    files:['pen_x1.png','pen_x2.png','pen_x3.png']
  }
};
```

Tilføj så en knap i positur-vælgeren:

```html
<button type="button" data-p="minNye" aria-pressed="false">Mit navn</button>
```

`portrait` er den tætte beskæring. Nemmeste måde at finde den på er at åbne siden,
vælge **Kvadrat**, og læse hvor pennen ligger — eller tage `penBBox` fra meta-filen og
lægge 5-10 % luft til.

`shadowGain` styrer hvor kraftig den syntetiske skygge er, hvis man slår den til. En
oprejst pen stabler hele sin længde sammen i en lille plet ved spidsen og har derfor
brug for en lavere værdi end en liggende: 0,10 mod 0,30 for de to eksisterende.

## Hvad `--denoise` gør

Et penskaft er en cylinder: langs pennen er lakken nærmest konstant, mens hele
skyggemodelleringen ligger på tværs. Derfor glattes der kraftigt *langs* aksen og
stort set ikke *på tværs*. Det fjerner JPEG-blokke uden at røre cylinderformen.
Standardværdien er 9 px. Er kilden tabsfri, kan man sætte den ned; `--denoise 0`
slår det fra.
