# Live Official Rome: procedura di collaudo

1. Caricare almeno un candidato originale verificato per categoria in `candidates/`, idealmente 2-3 per categoria.
2. Eseguire la validazione: nessun duplicato, articoli di almeno 800 parole, H2 finale `Informazioni sull'evento`, immagini e URL ufficiali.
3. Avviare il workflow di pubblicazione in modalità dry-run.
4. Configurare l'accesso autenticato a WordPress, verificando che il token e il metodo di autorizzazione siano compatibili con l'endpoint `/lor-importer/v1/run`. Non assumere che accetti Bearer token.
5. Eseguire un test di pubblicazione controllato, verificare per ogni articolo il post_id, la pagina pubblica, categoria, immagine e SEO.
6. Aggiornare l'indice anti-duplicati e ripulire soltanto le voci effettivamente processate.
7. Riattivare le automazioni ricorrenti solo dopo un collaudo 5/5 documentato.

ATTENZIONE: i workflow attuali sono una base sperimentale, non un sistema autonomo collaudato. Non garantiscono ancora aggiornamento automatico dell'indice o controllo pagina pubblica. In assenza di candidati la validazione fallisce intenzionalmente.
