"""Offline unit tests: no WordPress publications or GitHub mutations."""
import copy
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_batch as val
import publish_batch as pub


def fixture(category=169):
    return {
        "title": "Prova musicale dal vivo 2026 al Teatro Test",
        "slug": "prova-musicale-teatro-test-2026",
        "start": "2026-10-17 21:00:00",
        "end": "2026-10-17 23:00:00",
        "all_day": False,
        "timezone": "Europe/Rome",
        "cost": "10",
        "category_ids": [category],
        "event_url": "https://organizzatore.example/concerto-ottobre",
        "venue": {"name": "Teatro Test", "address": "Via Roma 1", "city": "Roma"},
        "image": {"url": "https://organizzatore.example/immagine.jpg",
                  "alt": "Concerto", "title": "Evento concerto"},
        "seo": {"focus_keyphrase": "Prova musicale 2026 Roma",
                "title": "Concerto di prova a Roma 2026",
                "meta_description": "Una serata di musica dal vivo a Roma, tutte le informazioni."},
        "content": "<h2>Introduzione</h2><p>" + "Musica originale a Roma. " * 230 +
                   "</p><h2>Informazioni sull'evento</h2><p>Consulta l'organizzatore.</p>",
    }


class ValidatorTests(unittest.TestCase):
    def test_valid_event(self):
        self.assertEqual(val.validate(fixture(), []), [])

    def test_exact_event_url_is_duplicate(self):
        self.assertIn("duplicate event URL", val.validate(fixture(), [fixture()]))

    def test_separate_shows_same_venue_same_day_allowed(self):
        other = fixture()
        other.update(title="Un'altra commedia con attori differenti",
                     slug="altra-commedia-teatro-2026",
                     start="2026-10-17 18:00:00",
                     end="2026-10-17 19:30:00",
                     event_url="https://organizzatore.example/commedia")
        other["seo"]["focus_keyphrase"] = "Altra commedia Roma"
        self.assertEqual(val.duplicate_reason(fixture(), other), None)

    def test_same_datetime_and_venue_blocked(self):
        old = fixture()
        old["slug"] = "diverso"
        old["event_url"] = "https://organizzatore.example/altro"
        old["seo"]["focus_keyphrase"] = "Altro evento"
        self.assertEqual(val.duplicate_reason(fixture(), old), "duplicate start datetime and venue")

    def test_short_article_rejected(self):
        e = fixture()
        e["content"] = "<h2>Informazioni sull'evento</h2><p>Breve</p>"
        self.assertIn("article must have at least 800 actual words", val.validate(e, []))

    def test_last_h2_required(self):
        e = fixture()
        e["content"] += "<h2>Altra sezione</h2><p>Fine</p>"
        self.assertTrue(any("last H2" in item for item in val.validate(e, [])))

    def test_priority_A_then_C(self):
        with tempfile.TemporaryDirectory() as path:
            root = pathlib.Path(path)
            (root / "candidates").mkdir()
            a = fixture()
            a["importance_level"] = "A"
            c = fixture()
            c["importance_level"] = "C"
            c["slug"] = "altro-artista"
            c["start"] = "2026-10-18 21:00:00"
            c["end"] = "2026-10-18 23:00:00"
            c["event_url"] = "https://organizzatore.example/altro-artista"
            c["seo"]["focus_keyphrase"] = "Altro artista Roma 2026"
            (root / "candidates" / "01-c.json").write_text(__import__("json").dumps(c))
            (root / "candidates" / "02-a.json").write_text(__import__("json").dumps(a))
            pools, rejected = val.select_candidates(root, [])
            self.assertFalse(rejected, rejected)
            self.assertEqual([e["importance_level"] for _, e in pools[169]], ["A", "C"])


class ControllerTests(unittest.TestCase):
    def test_index_update_is_idempotent(self):
        with tempfile.TemporaryDirectory() as path:
            root = pathlib.Path(path)
            (root / "data").mkdir()
            pub.write_json(root / "data/active-events-index.json", {"events": []})
            pub.write_json(root / "data/published-events-index.json", {"all_events": [], "active_index": []})
            with patch.object(pub, "ROOT", root):
                pub.synchronize_indexes(fixture(), 8000)
                pub.synchronize_indexes(fixture(), 8000)
            active = pub.load(root / "data/active-events-index.json")
            published = pub.load(root / "data/published-events-index.json")
            self.assertEqual(active["total_active_or_future_events"], 1)
            self.assertEqual(published["total_events"], 1)
            self.assertEqual(published["active_or_future_events"], 1)
            self.assertEqual(published["all_events"][0]["post_id"], 8000)

    def test_preflight_reports_auth_failure(self):
        with patch.dict(pub.os.environ, {"WP_APP_USER": "", "WP_APP_PASSWORD": "",
                                         "WP_IMPORTER_TOKEN": ""}):
            with self.assertRaisesRegex(pub.BatchFailure, "Missing"):
                pub.preflight()

    def test_preflight_success(self):
        def mock_api(path, **kwargs):
            if "users/me" in path:
                return {"id": 10}
            return {"status": "ok", "lock": False, "pending_count": 0,
                    "stale_processed_count": 0, "version": "1.2.1"}
        with patch.dict(pub.os.environ, {"WP_APP_USER": "editor",
                                         "WP_APP_PASSWORD": "fictional_test_only"}):
            with patch.object(pub, "api", side_effect=mock_api):
                self.assertEqual(pub.preflight()["user_id"], 10)

    def test_published_post_verified(self):
        candidate = fixture()
        record = {"post_id": 8000, "status": "published",
                  "url": pub.SITE + "/event/" + candidate["slug"] + "/"}
        event_response = {
            "status": "publish", "slug": candidate["slug"],
            "url": record["url"],
            "start_date": candidate["start"], "end_date": candidate["end"],
            "categories": [{"id": 169}],
            "image": {"id": 8100, "url": pub.SITE + "/img.jpg"},
            "website": candidate["event_url"],
            "description": candidate["content"],
        }
        seo_response = {"status": "publish", "yoast_head_json": {
            "title": candidate["seo"]["title"],
            "description": candidate["seo"]["meta_description"],
            "canonical": record["url"]}}
        with patch.object(pub, "api", side_effect=[event_response, seo_response]):
            result = pub.verify_published(candidate, record)
        self.assertEqual(result["post_id"], 8000)
        self.assertTrue(result["seo_verified"])

    def test_missing_image_blocks_confirmation(self):
        candidate = fixture()
        record = {"post_id": 8000, "status": "published",
                  "url": pub.SITE + "/event/" + candidate["slug"] + "/"}
        event_response = {
            "status": "publish", "slug": candidate["slug"],
            "url": record["url"],
            "start_date": candidate["start"], "end_date": candidate["end"],
            "categories": [{"id": 169}], "image": None,
            "website": candidate["event_url"], "description": candidate["content"],
        }
        with patch.object(pub, "api", side_effect=[event_response, {}]):
            with self.assertRaisesRegex(pub.BatchFailure, "featured image"):
                pub.verify_published(candidate, record)

    def test_unknown_import_never_replaces(self):
        candidate = fixture()
        with patch.object(pub, "stage", return_value="queue/unique.json"):
            with patch.object(pub, "api", side_effect=[
                {"processed": {}},
                {"processed_now": {}}, {"processed": {}}]):
                with self.assertRaises(pub.UncertainImport):
                    pub.process(pathlib.Path("test.json"), candidate, retries=1, poll_seconds=0)

    def test_explicit_duplicate_may_fallback(self):
        candidate = fixture()
        record = {"status": "duplicate", "post_id": 50}
        with patch.object(pub, "stage", return_value="queue/unique.json"):
            with patch.object(pub, "finish") as finish:
                with patch.object(pub, "api", side_effect=[
                    {"processed": {}},
                    {"processed_now": {}},
                    {"processed": {"queue/unique.json": record}}]):
                    result = pub.process(pathlib.Path("test.json"), candidate, retries=1, poll_seconds=0)
        self.assertEqual(result["status"], "duplicate")
        finish.assert_called_once()

    def test_unique_queue_file_names(self):
        # Avoid relying on fixed paths left in an importer's processed history.
        first = pub.uuid.uuid4().hex[:12]
        second = pub.uuid.uuid4().hex[:12]
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
