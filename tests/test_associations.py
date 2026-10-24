import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import associations

HAS_XDG = sys.platform.startswith("linux") and shutil.which("xdg-mime") is not None


class DesktopQuoteTest(unittest.TestCase):
    def test_quotes_special_characters(self):
        self.assertEqual(associations.desktop_quote("/a b/c"), '"/a b/c"')
        self.assertEqual(associations.desktop_quote('a"b$c`d\\e%f'), '"a\\"b\\$c\\`d\\\\e%%f"')


@unittest.skipUnless(HAS_XDG, "needs Linux with xdg-mime")
class LinuxAssociationsTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        env = {
            "HOME": self.home,
            "XDG_CONFIG_HOME": os.path.join(self.home, ".config"),
            "XDG_DATA_HOME": os.path.join(self.home, ".local", "share"),
            "XDG_CURRENT_DESKTOP": "",
            "DESKTOP_SESSION": "",
            "KDE_FULL_SESSION": "",
            "GNOME_DESKTOP_SESSION_ID": "",
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.home, True)

        os.makedirs(env["XDG_CONFIG_HOME"])
        os.makedirs(os.path.join(env["XDG_DATA_HOME"], "applications"))
        with open(os.path.join(env["XDG_DATA_HOME"], "applications", "other.desktop"), "w") as f:
            f.write("[Desktop Entry]\nName=Other\nExec=true %f\nType=Application\nMimeType=application/x-subrip;\n")
        with open(os.path.join(env["XDG_CONFIG_HOME"], "mimeapps.list"), "w") as f:
            f.write("[Default Applications]\napplication/x-subrip=other.desktop;\n")
        self.mimeapps = os.path.join(env["XDG_CONFIG_HOME"], "mimeapps.list")

    def test_install_and_restore(self):
        self.assertFalse(associations.associations_installed())

        associations.install_associations("/opt/my dir/aegi_rpc.py")
        self.assertTrue(associations.associations_installed())
        self.assertEqual(associations._xdg_default("application/x-subrip"), associations.DESKTOP_FILE)
        with open(os.path.join(associations._applications_dir(), associations.DESKTOP_FILE)) as f:
            self.assertIn('"/opt/my dir/aegi_rpc.py" %f', f.read())

        # Installing twice must not record our own handler as the "previous" one
        associations.install_associations("/opt/my dir/aegi_rpc.py")

        self.assertEqual(associations.remove_associations(), [])
        self.assertFalse(associations.associations_installed())
        self.assertEqual(associations._xdg_default("application/x-subrip"), "other.desktop")
        with open(self.mimeapps) as f:
            self.assertNotIn(associations.DESKTOP_FILE, f.read())
        self.assertFalse(os.path.exists(associations._backup_file()))

    def test_unset_removes_only_our_entry(self):
        with open(self.mimeapps, "w") as f:
            f.write(
                "[Added Associations]\ntext/x-ssa=aegi-rpc.desktop;\n\n"
                "[Default Applications]\ntext/x-ssa=aegi-rpc.desktop;keep.desktop;\n"
                "application/x-ssa=aegi-rpc.desktop;\n"
            )
        associations._unset_mime_default("text/x-ssa")
        associations._unset_mime_default("application/x-ssa")
        with open(self.mimeapps) as f:
            content = f.read()
        self.assertIn("[Added Associations]\ntext/x-ssa=aegi-rpc.desktop;", content)
        self.assertIn("text/x-ssa=keep.desktop;", content)
        self.assertNotIn("application/x-ssa", content)


if __name__ == "__main__":
    unittest.main()
