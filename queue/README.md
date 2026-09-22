# Live Official Rome Queue

Questa cartella viene letta automaticamente dal plugin WordPress **Live Official REST Bridge**.

Inserire qui solo file `.json` pronti per la pubblicazione. I file non JSON vengono ignorati.

Configurazione WordPress:
- Owner: `infoalessandromacci-rgb`
- Repository: `liveofficialrome-queue`
- Branch: `main`
- Cartella: `queue`
- Token GitHub: vuoto, perché il repository è pubblico

Un file JSON può contenere un singolo evento oppure un oggetto `{ "events": [ ... ] }`.
