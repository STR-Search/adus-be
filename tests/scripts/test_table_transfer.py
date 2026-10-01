import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/seeding_scripts/table_transfer.sh'


class TableTransferTests(unittest.TestCase):
    def run_script(self, *args):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / 'calls'
            for command in ('pg_dump', 'psql'):
                stub = root / command
                stub.write_text('#!/bin/bash\nprintf "%s\\n" "$0 $*" >> "$CALL_LOG"\n')
                stub.chmod(0o755)
            env = dict(os.environ, PATH=f'{root}:/usr/bin:/bin', CALL_LOG=str(log),
                       SOURCE_DATABASE_URL='postgresql://source/db',
                       DEV_DATABASE_URL='postgresql://destination/db')
            result = subprocess.run(['bash', str(SCRIPT), *args], env=env,
                                    capture_output=True, text=True)
            return result, log.read_text() if log.exists() else ''

    def test_uses_requested_schema_and_preserves_table_order(self):
        result, calls = self.run_script('--schema', 'users', '--tables', 'users,saved_searches')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--table="users"."users"', calls)
        self.assertIn('--table="users"."saved_searches"', calls)
        self.assertLess(calls.index('--table="users"."users"'), calls.index('--table="users"."saved_searches"'))
        self.assertIn('TRUNCATE TABLE "users"."users" RESTART IDENTITY CASCADE;', calls)
        self.assertIn('users.saved_searches', result.stdout)
        self.assertNotIn('iron_bank', calls)

    def test_invalid_arguments_never_access_database(self):
        for args in ((), ('--schema',), ('--schema', 'users'),
                     ('--schema', 'users', '--tables', 'users,bad;sql'),
                     ('--schema', 'users', '--tables', 'users,'),
                     ('--schema', 'public', '--tables', 'users'),
                     ('--schema', 'bad.schema', '--tables', 'users'),
                     ('--unknown', 'users')):
            with self.subTest(args=args):
                result, calls = self.run_script(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, '')

    def test_all_copies_each_schemas_configured_tables(self):
        expected = {
            'users': ['users', 'api_keys', 'saved_searches'],
            'markets': ['construction_costs_amenities', 'construction_costs_remodeling',
                        'realtors', 'market_keys_master', 'opex_by_bedrooms',
                        'opex_by_size', 'str_cribs_fee_details'],
            'reference': ['enum_options'],
            'iron_bank': ['underwritings', 'uw_comp_sets', 'uw_details',
                          'uw_operating_expenses', 'uw_optimization_items', 'uw_taxes', 'jobs'],
        }
        for schema, tables in expected.items():
            with self.subTest(schema=schema):
                result, calls = self.run_script('--schema', schema, '--tables', '--all')
                self.assertEqual(result.returncode, 0, result.stderr)
                dumped = [line.split('--table=')[1].split(' ')[0]
                          for line in calls.splitlines() if '--table=' in line]
                self.assertEqual(dumped, [f'"{schema}"."{table}"' for table in tables])

    def test_explicit_subset_accepts_spaces_after_commas(self):
        result, calls = self.run_script('--schema', 'users', '--tables', 'users,', 'saved_searches')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--table="users"."saved_searches"', calls)
        self.assertNotIn('--table="users"."api_keys"', calls)

    def test_unknown_schema_or_table_never_accesses_database(self):
        for schema, tables in [('unknown', '--all'), ('users', 'users,underwritings'),
                               ('markets', 'alembic_version')]:
            with self.subTest(schema=schema, tables=tables):
                result, calls = self.run_script('--schema', schema, '--tables', tables)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, '')

    def test_help_never_accesses_database(self):
        result, calls = self.run_script('--help')
        self.assertEqual(result.returncode, 0)
        self.assertIn('--schema', result.stdout)
        self.assertEqual(calls, '')
