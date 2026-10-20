from src.persistence import SQLiteProfileStore


def test_profile_store_round_trip(tmp_path):
    db_path = tmp_path / 'profiles.db'
    store = SQLiteProfileStore(str(db_path))
    store.save_profile({'name': 'alpha', 'dpi_scale': 1.25})
    profiles = store.list_profiles()
    assert any(p['name'] == 'alpha' for p in profiles)
