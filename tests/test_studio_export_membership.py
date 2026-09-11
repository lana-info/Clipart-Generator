"""Membership migration and persistence contracts, without generation services."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from studio_export_membership import validate_export_membership
from v3_project_state import ProjectState, save_project_draft, load_project_draft


class MembershipTests(unittest.TestCase):
    def test_draft_migration_backs_up_exact_original_once(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'draft.json'
            legacy = ProjectState().to_dict()
            legacy['clipart']['export_membership'] = {
                'missing.png': {'title': 'Old', 'included': False}}
            raw = json.dumps(legacy).encode()
            path.write_bytes(raw)
            state = load_project_draft(path)
            self.assertEqual(path.read_bytes(), raw)
            save_project_draft(state, path)
            backups = list(path.parent.glob('*.bak'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), raw)
            save_project_draft(load_project_draft(path), path)
            self.assertEqual(list(path.parent.glob('*.bak')), backups)
            self.assertFalse(load_project_draft(backups[0]).clipart.export_membership[
                'missing.png']['memberships'][0]['included'])

    def test_draft_migration_backup_value_error_is_project_state_error(self):
        from v3_project_state import ProjectStateError
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'draft.json'
            state = ProjectState()
            state.clipart.export_membership = validate_export_membership(
                {'one.png': {'title': 'Mini', 'included': True}})
            path.write_text('{}', encoding='utf-8')
            with patch('studio_export_membership.backup_membership_migration',
                       side_effect=ValueError('unsafe backup')):
                with self.assertRaises(ProjectStateError):
                    save_project_draft(state, path)

    def test_studio_migration_backup_failure_preserves_original(self):
        from studio_projects import ProjectStore, ProjectStoreError
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            legacy = ProjectState().to_dict()
            legacy['clipart']['export_membership'] = {
                'secret-garden.png': {'title': 'Old', 'included': False}}
            record = store.create('clipart', 'Old', legacy)
            path = Path(folder) / (record.project_id + '.json')
            original = path.read_bytes()
            migrated = ProjectState.from_dict(record.state).to_dict()
            with patch('studio_export_membership.backup_membership_migration', side_effect=OSError('disk full')):
                with self.assertRaises(ProjectStoreError):
                    store.save(record.project_id, 'clipart', 'Old', migrated)
            self.assertEqual(path.read_bytes(), original)
            store.save(record.project_id, 'clipart', 'Old', migrated)
            self.assertEqual(next(Path(folder).glob('*.bak')).read_bytes(), original)
            self.assertEqual(store.load(record.project_id).state, migrated)

    def test_rename_and_relocation_preserve_ids(self):
        value = validate_export_membership({'old.png': {'title': 'Mini', 'included': True}})
        original = copy.deepcopy(value['old.png'])
        value['new.png'] = value.pop('old.png')
        value['new.png']['memberships'][0]['title'] = 'Renamed'
        restored = validate_export_membership(value)['new.png']
        self.assertEqual(restored['asset_id'], original['asset_id'])
        self.assertEqual(restored['memberships'][0]['set_id'], original['memberships'][0]['set_id'])

    def test_legacy_migration_is_lossless_deterministic_and_detached(self):
        legacy = {'old.png': {'title': ' Garden ', 'included': False},
                  'other.png': {'title': ' Garden ', 'included': True}}
        original = copy.deepcopy(legacy)
        migrated = validate_export_membership(legacy)
        self.assertEqual(migrated['old.png']['version'], 2)
        a = migrated['old.png']['memberships'][0]
        b = migrated['other.png']['memberships'][0]
        self.assertEqual(a['set_id'], b['set_id'])
        self.assertEqual(a['title'], ' Garden ')
        self.assertFalse(a['included'])
        self.assertEqual(validate_export_membership(migrated), migrated)
        self.assertEqual(validate_export_membership(legacy), migrated)
        migrated['old.png']['memberships'][0]['included'] = True
        self.assertEqual(legacy, original)

    def test_four_memberships_roundtrip_and_independent_exclusion(self):
        value = validate_export_membership({'one.png': {'title': 'Mini', 'included': True}})
        item = value['one.png']
        for title in ('Standard', 'Maxi', 'Bundle'):
            link = validate_export_membership({'one.png': {'title': title, 'included': True}})
            item['memberships'].extend(link['one.png']['memberships'])
        original_id = item['asset_id']
        item['memberships'][1]['included'] = False
        state = ProjectState()
        state.clipart.export_membership = value
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'draft.json'
            save_project_draft(state, path)
            restored = load_project_draft(path).clipart.export_membership['one.png']
        self.assertEqual(restored['asset_id'], original_id)
        self.assertEqual([link['included'] for link in restored['memberships']], [True, False, True, True])
        self.assertEqual(restored, item)

    def test_invalid_new_links_are_rejected(self):
        value = validate_export_membership({'one.png': {'title': 'Mini', 'included': True}})
        for mutate in (
            lambda item: item.update(version=3),
            lambda item: item.update(asset_id='invalid'),
            lambda item: item['memberships'].append(copy.deepcopy(item['memberships'][0])),
            lambda item: item['memberships'][0].update(included='yes'),
            lambda item: item['memberships'][0].update(api_key='fixture'),
        ):
            bad = copy.deepcopy(value)
            mutate(bad['one.png'])
            with self.subTest(value=bad), self.assertRaises(ValueError):
                validate_export_membership(bad)
