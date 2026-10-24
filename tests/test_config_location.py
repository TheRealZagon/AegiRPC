import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import common

# Permission bits don't block root, and Windows ignores them for directories
CAN_LOCK = sys.platform != "win32" and hasattr(os, "geteuid") and os.geteuid() != 0


@unittest.skipUnless(CAN_LOCK, "needs a non-root POSIX user")
class ReadOnlyProgramFolderTest(unittest.TestCase):
    """AegiRPC sitting in a folder the user can't write to, like Program Files."""

    def setUp(self):
        base = tempfile.mkdtemp()
        self.home = os.path.join(base, "home")
        self.program_dir = os.path.join(base, "program")
        os.makedirs(self.home)
        os.makedirs(self.program_dir)
        self.local = os.path.join(self.program_dir, "config.xml")
        self.user = os.path.join(self.home, ".local", "share", "aegi_rpc", "config.xml")

        for patcher in (
            mock.patch.dict(os.environ, {"HOME": self.home}),
            mock.patch.object(sys, "argv", [os.path.join(self.program_dir, "aegi_rpc")]),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        old_cwd = os.getcwd()
        os.chdir(self.home)
        self.addCleanup(os.chdir, old_cwd)
        self.addCleanup(self._unlock_and_remove, base)

    @staticmethod
    def _unlock_and_remove(base):
        import shutil
        for root, dirs, files in os.walk(base):
            for name in dirs + files:
                os.chmod(os.path.join(root, name), stat.S_IRWXU)
        shutil.rmtree(base, True)

    def lock_program_dir(self):
        if os.path.exists(self.local):
            os.chmod(self.local, stat.S_IRUSR)
        os.chmod(self.program_dir, stat.S_IRUSR | stat.S_IXUSR)

    def test_default_is_created_in_user_folder(self):
        self.lock_program_dir()
        self.assertEqual(common.find_config_file(), self.user)
        self.assertTrue(os.path.isfile(self.user))

    def test_saving_falls_back_and_the_saved_copy_wins(self):
        common.write_config(self.local, common.DEFAULTS)
        self.lock_program_dir()

        # The read-only config next to the program is used until the user saves something
        self.assertEqual(common.find_config_file(), self.local)

        config = {**common.DEFAULTS, "hide_file_names": True}
        saved = common.save_config_file(self.local, config)
        self.assertEqual(saved, self.user)

        self.assertEqual(common.find_config_file(), self.user)
        self.assertTrue(common.read_config(self.user)["hide_file_names"])

    def test_writable_config_next_to_program_is_still_preferred(self):
        os.makedirs(os.path.dirname(self.user))
        common.write_config(self.local, common.DEFAULTS)
        common.write_config(self.user, common.DEFAULTS)
        self.assertEqual(common.find_config_file(), self.local)

    def test_no_fallback_when_already_in_user_folder(self):
        os.makedirs(os.path.dirname(self.user))
        os.chmod(os.path.dirname(self.user), stat.S_IRUSR | stat.S_IXUSR)
        with self.assertRaises(OSError):
            common.save_config_file(self.user, common.DEFAULTS)


if __name__ == "__main__":
    unittest.main()
