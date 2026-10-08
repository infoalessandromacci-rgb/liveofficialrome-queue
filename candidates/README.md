# Candidati verificati

Inserire qui file JSON con un evento per file, usando `docs/event-schema-example.json`.

Il controller non inventa eventi: richiede candidati verificati per tutte e cinque le categorie, preferibilmente con alternative.

Eseguire prima il workflow `Validate Live Official Rome 5-category batch`; solo dopo un esito positivo usare `Publish verified 5-category batch` con `apply=true`.

La pubblicazione richiede l'accesso autorizzato all'endpoint WordPress. Il solo caricamento di file non pubblica eventi.
