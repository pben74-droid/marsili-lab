# Marsili Lab Web

Dashboard pubblica di studio della sismicità nel Tirreno meridionale.

## Avvio

1. Carica **il contenuto** dello ZIP nella radice del repository pubblico `marsili-lab`.
2. Vai su **Settings → Actions → General → Workflow permissions** e seleziona **Read and write permissions** (se disponibile; altrimenti controlla che il workflow abbia il permesso di scrittura).
3. Vai su **Actions → Aggiorna catalogo INGV → Run workflow**. Attendi che il workflow termini con successo e crei `docs/data.json`.
4. Vai su **Settings → Pages → Build and deployment → Deploy from a branch → main → /docs → Save**.
5. Apri `https://pben74-droid.github.io/marsili-lab/`.

L'aggiornamento pianificato è ogni 15 minuti **best effort**: GitHub Actions può ritardare o saltare esecuzioni. Il sito mostra il timestamp dell'ultima acquisizione riuscita, non è un sistema di allerta in tempo reale.

## Fonti e limiti

- Eventi: INGV FDSNWS Event, `https://webservices.ingv.it/fdsnws/event/1/query`.
- Batimetria: layer EMODnet WMS, quando disponibile.
- Mappa: OpenStreetMap / Leaflet.
- Il catalogo INGV può essere rivisto. Le distanze sono geodetiche approssimate (Haversine) dalla sommità del Marsili, non dall'intero edificio vulcanico.
- Nessuna percentuale di origine magmatica è calcolabile dal solo catalogo; il progetto non prevede terremoti, tsunami o eruzioni.
