# Live Official Rome — Controller v2

## Componenti installati
- `scripts/validate_batch.py`: verifica JSON, 800+ parole, cinque categorie, finestra date, URL e duplicati; ordina i candidati A → B → C.
- `scripts/publish_batch.py`: preflight di autenticazione WordPress, pubblicazione da `candidates/*.json`, tentativi e sostituzioni sicure, verifica del post pubblicato tramite REST, sincronizzazione di entrambi gli indici e archivio dei JSON processati.
- `.github/workflows/controller-ci.yml`: ad ogni modifica a script o test esegue compilazione, unit test e preflight autenticato, **senza pubblicare nulla**. Scrive `data/controller-health.json` con il risultato e l'ID della run.
- `.github/workflows/publish-events.yml`: esecuzione **manuale** con scelta `preflight`, `dry-run`, `publish`. Pubblicazione solo se è selezionato espressamente `publish`.

## Prima di pubblicare
1. In GitHub Actions Secrets definire `WP_APP_USER` e `WP_APP_PASSWORD`, appartenenti **allo stesso utente** WordPress autorizzato. Usare una *password per applicazioni*, non la password di login ordinaria.
2. Aprire `data/controller-health.json` e verificare che `healthy` sia `true` e tutte le fasi risultino `success`.
3. Preparare nuovi file `candidates/*.json`, uno per evento, preferibilmente almeno 2 per categoria, con campi dello schema `docs/event-schema-example.json`. Gli eventi già pubblicati sono in `archive/candidates/` e non devono essere rimessi in `candidates/`.
4. Avviare prima `dry-run` e verificare `status: READY` nell'artefatto `live-rome-batch-audit`.
5. Solo dopo avviare `publish`. Il controller restringe automaticamente le date alla settimana successiva, da lunedì a domenica.
6. Dopo il run, verificare `status: COMPLETE`, cinque nuovi URL, cinque post pubblicati con foto, testi, Yoast e categorie. La coda deve essere vuota, gli indici aggiornati e i candidati pubblicati archiviati.

## Gestione errori
- Duplicato o errore definitivo dell'Importer: archivia il candidato come rifiutato e prova l'alternativa nella stessa categoria.
- Esito non accertabile o credenziali non valide: non inventa un successo; conserva la coda per ispezione ed evita di accodare eventi sostitutivi che potrebbero generare duplicati.
- Ogni post **verificato** aggiorna gli indici già durante l'esecuzione, così una successiva interruzione non perde i successi precedenti.
- I report GitHub non includono password né dati dei Secrets, ma soltanto presenza/assenza delle configurazioni e codici di errore.

## Stato del collaudo
- Pubblicazione manuale/importer: 5/5 verificati il 2026-10-08.
- Unit test controller: 15/15 passati nella run 37825472520.
- Preflight GitHub → WordPress: al 2026-10-08 WordPress ha restituito `HTTP 401 (incorrect_password)`; occorre correggere il Secret della password applicativa associata all'utente.
- **Non attivare la pubblicazione ricorrente finché `data/controller-health.json` non risulta healthy e non è stata eseguita una pubblicazione completa tramite il controller GitHub Actions.**

Link workflow: https://github.com/infoalessandromacci-rgb/liveofficialrome-queue/actions/workflows/publish-events.yml
