"""
    :synopsis: Unit Tests for Advanced Packaging Tool module 'module.aptpkg'
    :platform: Linux
    :maturity: develop
    versionadded:: 2017.7.0
"""


import copy
import logging
import textwrap

import pytest
import salt.modules.aptpkg as aptpkg
from salt.exceptions import CommandExecutionError, SaltInvocationError
from tests.support.mixins import LoaderModuleMockMixin
from tests.support.mock import MagicMock, Mock, call, patch
from tests.support.unit import TestCase, skipIf

log = logging.getLogger(__name__)


APT_KEY_LIST = r"""
pub:-:1024:17:46181433FBB75451:1104433784:::-:::scSC:
fpr:::::::::C5986B4F1257FFA86632CBA746181433FBB75451:
uid:-::::1104433784::B4D41942D4B35FF44182C7F9D00C99AF27B93AD0::Ubuntu CD Image Automatic Signing Key <cdimage@ubuntu.com>:
"""

REPO_KEYS = {
    "46181433FBB75451": {
        "algorithm": 17,
        "bits": 1024,
        "capability": "scSC",
        "date_creation": 1104433784,
        "date_expiration": None,
        "fingerprint": "C5986B4F1257FFA86632CBA746181433FBB75451",
        "keyid": "46181433FBB75451",
        "uid": "Ubuntu CD Image Automatic Signing Key <cdimage@ubuntu.com>",
        "uid_hash": "B4D41942D4B35FF44182C7F9D00C99AF27B93AD0",
        "validity": "-",
    }
}

PACKAGES = {"wget": "1.15-1ubuntu1.14.04.2"}

LOWPKG_FILES = {
    "errors": {},
    "packages": {
        "wget": [
            "/.",
            "/etc",
            "/etc/wgetrc",
            "/usr",
            "/usr/bin",
            "/usr/bin/wget",
            "/usr/share",
            "/usr/share/info",
            "/usr/share/info/wget.info.gz",
            "/usr/share/doc",
            "/usr/share/doc/wget",
            "/usr/share/doc/wget/MAILING-LIST",
            "/usr/share/doc/wget/NEWS.gz",
            "/usr/share/doc/wget/AUTHORS",
            "/usr/share/doc/wget/copyright",
            "/usr/share/doc/wget/changelog.Debian.gz",
            "/usr/share/doc/wget/README",
            "/usr/share/man",
            "/usr/share/man/man1",
            "/usr/share/man/man1/wget.1.gz",
        ]
    },
}

LOWPKG_INFO = {
    "wget": {
        "architecture": "amd64",
        "description": "retrieves files from the web",
        "homepage": "http://www.gnu.org/software/wget/",
        "install_date": "2016-08-30T22:20:15Z",
        "maintainer": "Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>",
        "name": "wget",
        "section": "web",
        "source": "wget",
        "version": "1.15-1ubuntu1.14.04.2",
        "status": "ii",
    },
    "apache2": {
        "architecture": "amd64",
        "description": """Apache HTTP Server
 The Apache HTTP Server Project's goal is to build a secure, efficient and
 extensible HTTP server as standards-compliant open source software. The
 result has long been the number one web server on the Internet.
 .
 Installing this package results in a full installation, including the
 configuration files, init scripts and support scripts.""",
        "homepage": "http://httpd.apache.org/",
        "install_date": "2016-08-30T22:20:15Z",
        "maintainer": "Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>",
        "name": "apache2",
        "section": "httpd",
        "source": "apache2",
        "version": "2.4.18-2ubuntu3.9",
        "status": "rc",
    },
}

APT_Q_UPDATE = """
Get:1 http://security.ubuntu.com trusty-security InRelease [65 kB]
Get:2 http://security.ubuntu.com trusty-security/main Sources [120 kB]
Get:3 http://security.ubuntu.com trusty-security/main amd64 Packages [548 kB]
Get:4 http://security.ubuntu.com trusty-security/main i386 Packages [507 kB]
Hit http://security.ubuntu.com trusty-security/main Translation-en
Fetched 1240 kB in 10s (124 kB/s)
Reading package lists...
"""

APT_Q_UPDATE_ERROR = """
Err http://security.ubuntu.com trusty InRelease

Err http://security.ubuntu.com trusty Release.gpg
Unable to connect to security.ubuntu.com:http:
Reading package lists...
W: Failed to fetch http://security.ubuntu.com/ubuntu/dists/trusty/InRelease

W: Failed to fetch http://security.ubuntu.com/ubuntu/dists/trusty/Release.gpg  Unable to connect to security.ubuntu.com:http:

W: Some index files failed to download. They have been ignored, or old ones used instead.
"""

AUTOREMOVE = """
Reading package lists... Done
Building dependency tree
Reading state information... Done
0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
"""

UPGRADE = """
Reading package lists...
Building dependency tree...
Reading state information...
0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
"""

UNINSTALL = {"tmux": {"new": "", "old": "1.8-5"}}
INSTALL = {"tmux": {"new": "1.8-5", "old": ""}}


def _get_uri(repo):
    """
    Get the URI portion of the a string
    """
    splits = repo.split()
    for val in splits:
        if any(val.startswith(x) for x in ("http://", "https://", "ftp://")):
            return val


class MockSourceEntry:
    def __init__(self, uri, source_type, line, invalid, file=None):
        self.uri = uri
        self.type = source_type
        self.line = line
        self.invalid = invalid
        self.file = file
        self.disabled = False
        self.dist = ""

    def mysplit(self, line):
        return line.split()


class MockSourceList:
    def __init__(self):
        self.list = []


class AptPkgTestCase(TestCase, LoaderModuleMockMixin):
    """
    Test cases for salt.modules.aptpkg
    """

    def setup_loader_modules(self):
        return {aptpkg: {"__grains__": {}}}

    @patch(
        "salt.modules.aptpkg.__salt__",
        {
            "pkg_resource.version": MagicMock(
                return_value=LOWPKG_INFO["wget"]["version"]
            )
        },
    )
    def test_version(self):
        """
        Test - Returns a string representing the package version or an empty string if
        not installed.
        """
        assert aptpkg.version(*["wget"]) == aptpkg.__salt__["pkg_resource.version"]()

    @patch("salt.modules.aptpkg.latest_version", MagicMock(return_value=""))
    def test_upgrade_available(self):
        """
        Test - Check whether or not an upgrade is available for a given package.
        """
        assert not aptpkg.upgrade_available("wget")

    @patch("salt.modules.aptpkg.get_repo_keys", MagicMock(return_value=REPO_KEYS))
    @patch(
        "salt.modules.aptpkg.__salt__",
        {"cmd.run_all": MagicMock(return_value={"retcode": 0, "stdout": "OK"})},
    )
    def test_add_repo_key(self):
        """
        Test - Add a repo key.
        """
        assert aptpkg.add_repo_key(keyserver="keyserver.ubuntu.com", keyid="FBB75451")

    @patch("salt.modules.aptpkg.get_repo_keys", MagicMock(return_value=REPO_KEYS))
    @patch(
        "salt.modules.aptpkg.__salt__",
        {"cmd.run_all": MagicMock(return_value={"retcode": 0, "stdout": "OK"})},
    )
    def test_add_repo_key_failed(self):
        """
        Test - Add a repo key using incomplete input data.
        """
        with pytest.raises(SaltInvocationError) as ex:
            aptpkg.add_repo_key(keyserver="keyserver.ubuntu.com")
        assert (
            " No keyid or keyid too short for keyserver: keyserver.ubuntu.com"
            in str(ex)
        )

    def test_get_repo_keys(self):
        """
        Test - List known repo key details.
        """
        mock = MagicMock(return_value={"retcode": 0, "stdout": APT_KEY_LIST})
        with patch.dict(aptpkg.__salt__, {"cmd.run_all": mock}):
            self.assertEqual(aptpkg.get_repo_keys(), REPO_KEYS)

    @patch(
        "salt.modules.aptpkg.__salt__",
        {"lowpkg.file_dict": MagicMock(return_value=LOWPKG_FILES)},
    )
    def test_file_dict(self):
        """
        Test - List the files that belong to a package, grouped by package.
        """
        assert aptpkg.file_dict("wget") == LOWPKG_FILES

    @patch(
        "salt.modules.aptpkg.__salt__",
        {
            "lowpkg.file_list": MagicMock(
                return_value={
                    "errors": LOWPKG_FILES["errors"],
                    "files": LOWPKG_FILES["packages"]["wget"],
                }
            )
        },
    )
    def test_file_list(self):
        """
        Test 'file_list' function, which is just an alias to the lowpkg 'file_list'

        """
        assert aptpkg.file_list("wget") == aptpkg.__salt__["lowpkg.file_list"]()

    @patch(
        "salt.modules.aptpkg.__salt__",
        {"cmd.run_stdout": MagicMock(return_value="wget\t\t\t\t\t\tinstall")},
    )
    def test_get_selections(self):
        """
        Test - View package state from the dpkg database.
        """
        assert aptpkg.get_selections("wget") == {"install": ["wget"]}

    @patch(
        "salt.modules.aptpkg.__salt__",
        {"lowpkg.info": MagicMock(return_value=LOWPKG_INFO)},
    )
    def test_info_installed(self):
        """
        Test - Return the information of the named package(s) installed on the system.
        """
        names = {"group": "section", "packager": "maintainer", "url": "homepage"}

        installed = copy.deepcopy({"wget": LOWPKG_INFO["wget"]})
        for name in names:
            if installed["wget"].get(names[name], False):
                installed["wget"][name] = installed["wget"].pop(names[name])

        del installed["wget"]["status"]
        self.assertEqual(aptpkg.info_installed("wget"), installed)
        self.assertEqual(len(aptpkg.info_installed()), 1)

    def test_info_installed_attr_without_status(self):
        """
        Test info_installed 'attr' for inclusion of 'status' attribute.

        Since info_installed should only return installed packages, we need to
        call __salt__['lowpkg.info'] with the 'status' attribute even if the user
        is not asking for it in 'attr'. Otherwise info_installed would not be able
        to check if the package is installed and would return everything.

        :return:
        """
        with patch(
            "salt.modules.aptpkg.__salt__",
            {"lowpkg.info": MagicMock(return_value=LOWPKG_INFO)},
        ) as wget_lowpkg:
            ret = aptpkg.info_installed("wget", attr="version")
            calls = wget_lowpkg["lowpkg.info"].call_args_list.pop()
            self.assertIn("status", calls.kwargs["attr"])
            self.assertIn("version", calls.kwargs["attr"])

    @patch(
        "salt.modules.aptpkg.__salt__",
        {"lowpkg.info": MagicMock(return_value=LOWPKG_INFO)},
    )
    def test_info_installed_attr(self):
        """
        Test info_installed 'attr'.
        This doesn't test 'attr' behaviour per se, since the underlying function is in dpkg.
        The test should simply not raise exceptions for invalid parameter.

        :return:
        """
        ret = aptpkg.info_installed("emacs", attr="foo,bar")
        assert isinstance(ret, dict)
        assert "wget" in ret
        assert isinstance(ret["wget"], dict)

        wget_pkg = ret["wget"]
        expected_pkg = {
            "url": "http://www.gnu.org/software/wget/",
            "packager": "Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>",
            "name": "wget",
            "install_date": "2016-08-30T22:20:15Z",
            "description": "retrieves files from the web",
            "version": "1.15-1ubuntu1.14.04.2",
            "architecture": "amd64",
            "group": "web",
            "source": "wget",
        }
        for k in wget_pkg:
            assert k in expected_pkg
            assert wget_pkg[k] == expected_pkg[k]

    @patch(
        "salt.modules.aptpkg.__salt__",
        {"lowpkg.info": MagicMock(return_value=LOWPKG_INFO)},
    )
    def test_info_installed_all_versions(self):
        """
        Test info_installed 'all_versions'.
        Since Debian won't return same name packages with the different names,
        this should just return different structure, backward compatible with
        the RPM equivalents.

        :return:
        """
        print()
        ret = aptpkg.info_installed("emacs", all_versions=True)
        assert isinstance(ret, dict)
        assert "wget" in ret
        assert isinstance(ret["wget"], list)

        pkgs = ret["wget"]

        assert len(pkgs) == 1
        assert isinstance(pkgs[0], dict)

        wget_pkg = pkgs[0]
        expected_pkg = {
            "url": "http://www.gnu.org/software/wget/",
            "packager": "Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>",
            "name": "wget",
            "install_date": "2016-08-30T22:20:15Z",
            "description": "retrieves files from the web",
            "version": "1.15-1ubuntu1.14.04.2",
            "architecture": "amd64",
            "group": "web",
            "source": "wget",
        }
        for k in wget_pkg:
            assert k in expected_pkg
            assert wget_pkg[k] == expected_pkg[k]

    @patch(
        "salt.modules.aptpkg.__salt__",
        {"cmd.run_stdout": MagicMock(return_value="wget: /usr/bin/wget")},
    )
    def test_owner(self):
        """
        Test - Return the name of the package that owns the file.
        """
        assert aptpkg.owner("/usr/bin/wget") == "wget"

    @patch("salt.utils.pkg.clear_rtag", MagicMock())
    @patch(
        "salt.modules.aptpkg.__salt__",
        {
            "cmd.run_all": MagicMock(
                return_value={"retcode": 0, "stdout": APT_Q_UPDATE}
            ),
            "config.get": MagicMock(return_value=False),
        },
    )
    def test_refresh_db(self):
        """
        Test - Updates the APT database to latest packages based upon repositories.
        """
        refresh_db = {
            "http://security.ubuntu.com trusty-security InRelease": True,
            "http://security.ubuntu.com trusty-security/main Sources": True,
            "http://security.ubuntu.com trusty-security/main Translation-en": None,
            "http://security.ubuntu.com trusty-security/main amd64 Packages": True,
            "http://security.ubuntu.com trusty-security/main i386 Packages": True,
        }
        mock = MagicMock(return_value={"retcode": 0, "stdout": APT_Q_UPDATE})
        with patch("salt.utils.pkg.clear_rtag", MagicMock()):
            with patch.dict(
                aptpkg.__salt__,
                {"cmd.run_all": mock, "config.get": MagicMock(return_value=False)},
            ):
                self.assertEqual(aptpkg.refresh_db(), refresh_db)

    @patch("salt.utils.pkg.clear_rtag", MagicMock())
    @patch(
        "salt.modules.aptpkg.__salt__",
        {
            "cmd.run_all": MagicMock(
                return_value={"retcode": 0, "stdout": APT_Q_UPDATE_ERROR}
            ),
            "config.get": MagicMock(return_value=False),
        },
    )
    def test_refresh_db_failed(self):
        """
        Test - Update the APT database using unreachable repositories.
        """
        kwargs = {"failhard": True}
        mock = MagicMock(return_value={"retcode": 0, "stdout": APT_Q_UPDATE_ERROR})
        with patch("salt.utils.pkg.clear_rtag", MagicMock()):
            with patch.dict(
                aptpkg.__salt__,
                {"cmd.run_all": mock, "config.get": MagicMock(return_value=False)},
            ):
                self.assertRaises(CommandExecutionError, aptpkg.refresh_db, **kwargs)

    def test_autoremove(self):
        """
        Test - Remove packages not required by another package.
        """
        with patch("salt.modules.aptpkg.list_pkgs", MagicMock(return_value=PACKAGES)):
            patch_kwargs = {
                "__salt__": {
                    "config.get": MagicMock(return_value=True),
                    "cmd.run_all": MagicMock(
                        return_value=MagicMock(return_value=AUTOREMOVE)
                    ),
                }
            }
            with patch.multiple(aptpkg, **patch_kwargs):
                assert aptpkg.autoremove() == {}
                assert aptpkg.autoremove(purge=True) == {}
                assert aptpkg.autoremove(list_only=True) == []
                assert aptpkg.autoremove(list_only=True, purge=True) == []

    @patch("salt.modules.aptpkg._uninstall", MagicMock(return_value=UNINSTALL))
    def test_remove(self):
        """
        Test - Remove packages.
        """
        assert aptpkg.remove(name="tmux") == UNINSTALL

    @patch("salt.modules.aptpkg._uninstall", MagicMock(return_value=UNINSTALL))
    def test_purge(self):
        """
        Test - Remove packages along with all configuration files.
        """
        assert aptpkg.purge(name="tmux") == UNINSTALL

    @patch("salt.utils.pkg.clear_rtag", MagicMock())
    @patch("salt.modules.aptpkg.list_pkgs", MagicMock(return_value=UNINSTALL))
    @patch.multiple(
        aptpkg,
        **{
            "__salt__": {
                "config.get": MagicMock(return_value=True),
                "cmd.run_all": MagicMock(
                    return_value={"retcode": 0, "stdout": UPGRADE}
                ),
            }
        }
    )
    def test_upgrade(self):
        """
        Test - Upgrades all packages.
        """
        with patch("salt.utils.pkg.clear_rtag", MagicMock()):
            with patch(
                "salt.modules.aptpkg.list_pkgs", MagicMock(return_value=UNINSTALL)
            ):
                mock_cmd = MagicMock(return_value={"retcode": 0, "stdout": UPGRADE})
                patch_kwargs = {
                    "__salt__": {
                        "config.get": MagicMock(return_value=True),
                        "cmd.run_all": mock_cmd,
                    }
                }
                with patch.multiple(aptpkg, **patch_kwargs):
                    self.assertEqual(aptpkg.upgrade(), dict())
                    kwargs = {"force_conf_new": True}
                    self.assertEqual(aptpkg.upgrade(**kwargs), dict())

    def test_upgrade_downloadonly(self):
        """
        Tests the download-only options for upgrade.
        """
        with patch("salt.utils.pkg.clear_rtag", MagicMock()):
            with patch(
                "salt.modules.aptpkg.list_pkgs", MagicMock(return_value=UNINSTALL)
            ):
                mock_cmd = MagicMock(return_value={"retcode": 0, "stdout": UPGRADE})
                patch_kwargs = {
                    "__salt__": {
                        "config.get": MagicMock(return_value=True),
                        "cmd.run_all": mock_cmd,
                    },
                }
                with patch.multiple(aptpkg, **patch_kwargs):
                    aptpkg.upgrade()
                    args_matching = [
                        True
                        for args in patch_kwargs["__salt__"]["cmd.run_all"].call_args[0]
                        if "--download-only" in args
                    ]
                    # Here we shouldn't see the parameter and args_matching should be empty.
                    self.assertFalse(any(args_matching))

                    aptpkg.upgrade(downloadonly=True)
                    args_matching = [
                        True
                        for args in patch_kwargs["__salt__"]["cmd.run_all"].call_args[0]
                        if "--download-only" in args
                    ]
                    # --download-only should be in the args list and we should have at least on True in the list.
                    self.assertTrue(any(args_matching))

                    aptpkg.upgrade(download_only=True)
                    args_matching = [
                        True
                        for args in patch_kwargs["__salt__"]["cmd.run_all"].call_args[0]
                        if "--download-only" in args
                    ]
                    # --download-only should be in the args list and we should have at least on True in the list.
                    self.assertTrue(any(args_matching))

    def test_show(self):
        """
        Test that the pkg.show function properly parses apt-cache show output.
        This test uses an abridged output per package, for simplicity.
        """
        show_mock_success = MagicMock(
            return_value={
                "retcode": 0,
                "pid": 12345,
                "stderr": "",
                "stdout": textwrap.dedent(
                    """\
                Package: foo1.0
                Architecture: amd64
                Version: 1.0.5-3ubuntu4
                Description: A silly package (1.0 release cycle)
                Provides: foo
                Suggests: foo-doc

                Package: foo1.0
                Architecture: amd64
                Version: 1.0.4-2ubuntu1
                Description: A silly package (1.0 release cycle)
                Provides: foo
                Suggests: foo-doc

                Package: foo-doc
                Architecture: all
                Version: 1.0.5-3ubuntu4
                Description: Silly documentation for a silly package (1.0 release cycle)

                Package: foo-doc
                Architecture: all
                Version: 1.0.4-2ubuntu1
                Description: Silly documentation for a silly package (1.0 release cycle)

                """
                ),
            }
        )

        show_mock_failure = MagicMock(
            return_value={
                "retcode": 1,
                "pid": 12345,
                "stderr": textwrap.dedent(
                    """\
                N: Unable to locate package foo*
                N: Couldn't find any package by glob 'foo*'
                N: Couldn't find any package by regex 'foo*'
                E: No packages found
                """
                ),
                "stdout": "",
            }
        )

        refresh_mock = Mock()

        expected = {
            "foo1.0": {
                "1.0.5-3ubuntu4": {
                    "Architecture": "amd64",
                    "Description": "A silly package (1.0 release cycle)",
                    "Provides": "foo",
                    "Suggests": "foo-doc",
                },
                "1.0.4-2ubuntu1": {
                    "Architecture": "amd64",
                    "Description": "A silly package (1.0 release cycle)",
                    "Provides": "foo",
                    "Suggests": "foo-doc",
                },
            },
            "foo-doc": {
                "1.0.5-3ubuntu4": {
                    "Architecture": "all",
                    "Description": "Silly documentation for a silly package (1.0 release cycle)",
                },
                "1.0.4-2ubuntu1": {
                    "Architecture": "all",
                    "Description": "Silly documentation for a silly package (1.0 release cycle)",
                },
            },
        }

        # Make a copy of the above dict and strip out some keys to produce the
        # expected filtered result.
        filtered = copy.deepcopy(expected)
        for k1 in filtered:
            for k2 in filtered[k1]:
                # Using list() because we will modify the dict during iteration
                for k3 in list(filtered[k1][k2]):
                    if k3 not in ("Description", "Provides"):
                        filtered[k1][k2].pop(k3)

        with patch.dict(
            aptpkg.__salt__, {"cmd.run_all": show_mock_success}
        ), patch.object(aptpkg, "refresh_db", refresh_mock):

            # Test success (no refresh)
            self.assertEqual(aptpkg.show("foo*"), expected)
            refresh_mock.assert_not_called()
            refresh_mock.reset_mock()

            # Test success (with refresh)
            self.assertEqual(aptpkg.show("foo*", refresh=True), expected)
            self.assert_called_once(refresh_mock)
            refresh_mock.reset_mock()

            # Test filtered return
            self.assertEqual(
                aptpkg.show("foo*", filter="description,provides"), filtered
            )
            refresh_mock.assert_not_called()
            refresh_mock.reset_mock()

        with patch.dict(
            aptpkg.__salt__, {"cmd.run_all": show_mock_failure}
        ), patch.object(aptpkg, "refresh_db", refresh_mock):

            # Test failure (no refresh)
            self.assertEqual(aptpkg.show("foo*"), {})
            refresh_mock.assert_not_called()
            refresh_mock.reset_mock()

            # Test failure (with refresh)
            self.assertEqual(aptpkg.show("foo*", refresh=True), {})
            self.assert_called_once(refresh_mock)
            refresh_mock.reset_mock()

    def test_mod_repo_enabled(self):
        """
        Checks if a repo is enabled or disabled depending on the passed kwargs.
        """
        with patch.dict(
            aptpkg.__salt__,
            {"config.option": MagicMock(), "no_proxy": MagicMock(return_value=False)},
        ):
            with patch("salt.modules.aptpkg._check_apt", MagicMock(return_value=True)):
                with patch(
                    "salt.modules.aptpkg.refresh_db", MagicMock(return_value={})
                ):
                    with patch(
                        "salt.utils.data.is_true", MagicMock(return_value=True)
                    ) as data_is_true:
                        with patch(
                            "salt.modules.aptpkg.sourceslist", MagicMock(), create=True
                        ):
                            repo = aptpkg.mod_repo("foo", enabled=False)
                            data_is_true.assert_called_with(False)
                            # with disabled=True; should call salt.utils.data.is_true True
                            data_is_true.reset_mock()
                            repo = aptpkg.mod_repo("foo", disabled=True)
                            data_is_true.assert_called_with(True)
                            # with enabled=True; should call salt.utils.data.is_true with False
                            data_is_true.reset_mock()
                            repo = aptpkg.mod_repo("foo", enabled=True)
                            data_is_true.assert_called_with(True)
                            # with disabled=True; should call salt.utils.data.is_true False
                            data_is_true.reset_mock()
                            repo = aptpkg.mod_repo("foo", disabled=False)
                            data_is_true.assert_called_with(False)

    @patch(
        "salt.utils.path.os_walk", MagicMock(return_value=[("test", "test", "test")])
    )
    @patch("os.path.getsize", MagicMock(return_value=123456))
    @patch("os.path.getctime", MagicMock(return_value=1234567890.123456))
    @patch(
        "fnmatch.filter",
        MagicMock(return_value=["/var/cache/apt/archive/test_package.rpm"]),
    )
    def test_list_downloaded(self):
        """
        Test downloaded packages listing.
        :return:
        """
        DOWNLOADED_RET = {
            "test-package": {
                "1.0": {
                    "path": "/var/cache/apt/archive/test_package.rpm",
                    "size": 123456,
                    "creation_date_time_t": 1234567890,
                    "creation_date_time": "2009-02-13T23:31:30",
                }
            }
        }

        with patch.dict(
            aptpkg.__salt__,
            {
                "lowpkg.bin_pkg_info": MagicMock(
                    return_value={"name": "test-package", "version": "1.0"}
                )
            },
        ):
            list_downloaded = aptpkg.list_downloaded()
            self.assertEqual(len(list_downloaded), 1)
            self.assertDictEqual(list_downloaded, DOWNLOADED_RET)

    def test__skip_source(self):
        """
        Test __skip_source.
        :return:
        """
        # Valid source
        source_type = "deb"
        source_uri = "http://cdn-aws.deb.debian.org/debian"
        source_line = "deb http://cdn-aws.deb.debian.org/debian stretch main\n"

        mock_source = MockSourceEntry(source_uri, source_type, source_line, False)

        ret = aptpkg._skip_source(mock_source)
        self.assertFalse(ret)

        # Invalid source type
        source_type = "ded"
        source_uri = "http://cdn-aws.deb.debian.org/debian"
        source_line = "deb http://cdn-aws.deb.debian.org/debian stretch main\n"

        mock_source = MockSourceEntry(source_uri, source_type, source_line, True)

        ret = aptpkg._skip_source(mock_source)
        self.assertTrue(ret)

        # Invalid source type , not skipped
        source_type = "deb"
        source_uri = "http://cdn-aws.deb.debian.org/debian"
        source_line = "deb [http://cdn-aws.deb.debian.org/debian] stretch main\n"

        mock_source = MockSourceEntry(source_uri, source_type, source_line, True)

        ret = aptpkg._skip_source(mock_source)
        self.assertFalse(ret)

    def test_normalize_name(self):
        """
        Test that package is normalized only when it should be
        """
        with patch.dict(aptpkg.__grains__, {"osarch": "amd64"}):
            result = aptpkg.normalize_name("foo")
            assert result == "foo", result
            result = aptpkg.normalize_name("foo:amd64")
            assert result == "foo", result
            result = aptpkg.normalize_name("foo:any")
            assert result == "foo", result
            result = aptpkg.normalize_name("foo:all")
            assert result == "foo", result
            result = aptpkg.normalize_name("foo:i386")
            assert result == "foo:i386", result

    def test_list_repos(self):
        """
        Checks results from list_repos
        """
        # Valid source
        source_type = "deb"
        source_uri = "http://cdn-aws.deb.debian.org/debian/"
        source_line = "deb http://cdn-aws.deb.debian.org/debian/ stretch main\n"

        mock_source = MockSourceEntry(source_uri, source_type, source_line, False)
        mock_source_list = MockSourceList()
        mock_source_list.list = [mock_source]

        with patch("salt.modules.aptpkg._check_apt", MagicMock(return_value=True)):
            with patch("salt.modules.aptpkg.sourceslist", MagicMock(), create=True):
                with patch(
                    "salt.modules.aptpkg.sourceslist.SourcesList",
                    MagicMock(return_value=mock_source_list),
                    create=True,
                ):
                    repos = aptpkg.list_repos()
                    self.assertIn(source_uri, repos)

                    assert isinstance(repos[source_uri], list)
                    assert len(repos[source_uri]) == 1

                    # Make sure last character in of the URI in line is still a /
                    self.assertIn("line", repos[source_uri][0])
                    _uri = _get_uri(repos[source_uri][0]["line"])
                    self.assertEqual(_uri[-1], "/")

                    # Make sure last character in URI is still a /
                    self.assertIn("uri", repos[source_uri][0])
                    self.assertEqual(repos[source_uri][0]["uri"][-1], "/")

    def test_expand_repo_def(self):
        """
        Checks results from expand_repo_def
        """
        source_type = "deb"
        source_uri = "http://cdn-aws.deb.debian.org/debian/"
        source_line = "deb http://cdn-aws.deb.debian.org/debian/ stretch main\n"
        source_file = "/etc/apt/sources.list"

        mock_source = MockSourceEntry(
            source_uri, source_type, source_line, False, file=source_file
        )

        # Valid source
        with patch("salt.modules.aptpkg._check_apt", MagicMock(return_value=True)):
            with patch("salt.modules.aptpkg.sourceslist", MagicMock(), create=True):
                with patch(
                    "salt.modules.aptpkg.sourceslist.SourceEntry",
                    MagicMock(return_value=mock_source),
                    create=True,
                ):
                    repo = "deb http://cdn-aws.deb.debian.org/debian/ stretch main\n"
                    sanitized = aptpkg.expand_repo_def(repo=repo, file=source_file)

                    assert isinstance(sanitized, dict)
                    self.assertIn("uri", sanitized)

                    # Make sure last character in of the URI is still a /
                    self.assertEqual(sanitized["uri"][-1], "/")


@skipIf(pytest is None, "PyTest is missing")
class AptUtilsTestCase(TestCase, LoaderModuleMockMixin):
    """
    apt utils test case
    """

    def setup_loader_modules(self):
        return {aptpkg: {}}

    def test_call_apt_default(self):
        """
        Call default apt.
        :return:
        """
        with patch.dict(
            aptpkg.__salt__,
            {"cmd.run_all": MagicMock(), "config.get": MagicMock(return_value=False)},
        ):
            aptpkg._call_apt(["apt-get", "install", "emacs"])  # pylint: disable=W0106
            aptpkg.__salt__["cmd.run_all"].assert_called_once_with(
                ["apt-get", "install", "emacs"],
                env={},
                output_loglevel="trace",
                python_shell=False,
            )

    @patch("salt.utils.systemd.has_scope", MagicMock(return_value=True))
    def test_call_apt_in_scope(self):
        """
        Call apt within the scope.
        :return:
        """
        with patch.dict(
            aptpkg.__salt__,
            {"cmd.run_all": MagicMock(), "config.get": MagicMock(return_value=True)},
        ):
            aptpkg._call_apt(["apt-get", "purge", "vim"])  # pylint: disable=W0106
            aptpkg.__salt__["cmd.run_all"].assert_called_once_with(
                [
                    "systemd-run",
                    "--scope",
                    "--description",
                    '"salt.modules.aptpkg"',
                    "apt-get",
                    "purge",
                    "vim",
                ],
                env={},
                output_loglevel="trace",
                python_shell=False,
            )

    def test_call_apt_with_kwargs(self):
        """
        Call apt with the optinal keyword arguments.
        :return:
        """
        with patch.dict(
            aptpkg.__salt__,
            {"cmd.run_all": MagicMock(), "config.get": MagicMock(return_value=False)},
        ):
            aptpkg._call_apt(
                ["dpkg", "-l", "python"],
                python_shell=True,
                output_loglevel="quiet",
                ignore_retcode=False,
                username="Darth Vader",
            )  # pylint: disable=W0106
            aptpkg.__salt__["cmd.run_all"].assert_called_once_with(
                ["dpkg", "-l", "python"],
                env={},
                ignore_retcode=False,
                output_loglevel="quiet",
                python_shell=True,
                username="Darth Vader",
            )

    def test_call_apt_dpkg_lock(self):
        """
        Call apt and ensure the dpkg locking is handled
        :return:
        """
        cmd_side_effect = [
            {"stderr": "Could not get lock"},
            {"stderr": "Could not get lock"},
            {"stderr": "Could not get lock"},
            {"stderr": "Could not get lock"},
            {"stderr": "", "stdout": ""},
        ]

        cmd_mock = MagicMock(side_effect=cmd_side_effect)
        cmd_call = (
            call(
                ["dpkg", "-l", "python"],
                env={},
                ignore_retcode=False,
                output_loglevel="quiet",
                python_shell=True,
                username="Darth Vader",
            ),
        )
        expected_calls = [cmd_call * 5]

        with patch.dict(
            aptpkg.__salt__,
            {"cmd.run_all": cmd_mock, "config.get": MagicMock(return_value=False)},
        ):
            with patch("salt.modules.aptpkg.time.sleep", MagicMock()) as sleep_mock:
                aptpkg._call_apt(
                    ["dpkg", "-l", "python"],
                    python_shell=True,
                    output_loglevel="quiet",
                    ignore_retcode=False,
                    username="Darth Vader",
                )  # pylint: disable=W0106

                # We should have sleept at least 4 times
                assert sleep_mock.call_count >= 4

                # We should attempt to call the cmd 5 times
                self.assertEqual(cmd_mock.call_count, 5)
                cmd_mock.has_calls(expected_calls)

    @patch("salt.utils.path.which_bin", Mock(return_value="/usr/sbin/checkrestart"))
    def test_services_need_restart(self):
        """
        Test that checkrestart output is parsed correctly
        """
        cr_output = """
PROCESSES: 24
PROGRAMS: 17
PACKAGES: 8
SERVICE:rsyslog,385,/usr/sbin/rsyslogd
SERVICE:cups-daemon,390,/usr/sbin/cupsd
       """

        with patch.dict(
            aptpkg.__salt__, {"cmd.run_stdout": Mock(return_value=cr_output)}
        ):
            assert sorted(aptpkg.services_need_restart()) == [
                "cups-daemon",
                "rsyslog",
            ]
