# coding: utf-8
"""Run several jobs sharing a session using a configuration file.
"""
from __future__ import absolute_import
from __future__ import unicode_literals

import io
import getpass
import logging
import typing
import traceback
import six
import verboselogs
from requests import Session

from .looters import HashtagLooter, ProfileLooter
from .pbar import TqdmProgressBar
from .time import get_times_from_cli

if typing.TYPE_CHECKING:
    from typing import Any, Dict, Mapping, Optional, Text, Type, Union
    from .looter import InstaLooter


#: The module logger
logger = verboselogs.VerboseLogger(__name__)


class BatchRunner(object):
    """Run ``InstaLooter`` in batch mode, using a configuration file.
    """

    _CLS_MAP = {
        'users': ProfileLooter,
        'hashtag': HashtagLooter,
    }  # type: Mapping[Text, Type[InstaLooter]]

    def __init__(self, handle, args=None):
        # type: (Any, Optional[Mapping[Text, Any]]) -> None

        close_handle = False
        if isinstance(handle, six.binary_type):
            handle = handle.decode('utf-8')
        if isinstance(handle, six.text_type):
            _handle = open(handle)  # type: typing.IO
            close_handle = True
        else:
            _handle = handle

        try:
            self.args = args or {}
            self.parser = six.moves.configparser.ConfigParser()
            getattr(self.parser, "readfp" if six.PY2 else "read_file")(_handle)
        finally:
            if close_handle:
                _handle.close()

    @typing.overload
    def _getboolean(self, section_id, key, default):
        # type: (Text, Text, bool) -> bool
        pass

    @typing.overload
    def _getboolean(self, section_id, key):
        # type: (Text, Text) -> Optional[bool]
        pass

    @typing.overload
    def _getboolean(self, section_id, key, default):
        # type: (Text, Text, None) -> Optional[bool]
        pass

    def _getboolean(self, section_id, key, default=None):
        # type: (Text, Text, Optional[bool]) -> Optional[bool]
        if self.parser.has_option(section_id, key):
            return self.parser.getboolean(section_id, key)
        return default

    @typing.overload
    def _getint(self, section_id, key, default):
        # type: (Text, Text, None) -> Optional[int]
        pass

    @typing.overload
    def _getint(self, section_id, key):
        # type: (Text, Text) -> Optional[int]
        pass

    @typing.overload
    def _getint(self, section_id, key, default):
        # type: (Text, Text, int) -> int
        pass

    def _getint(self, section_id, key, default=None):
        # type: (Text, Text, Optional[int]) -> Optional[int]
        if self.parser.has_option(section_id, key):
            return self.parser.getint(section_id, key)
        return default

    @typing.overload
    def _get(self, section_id, key, default):
        # type: (Text, Text, None) -> Optional[Text]
        pass

    @typing.overload
    def _get(self, section_id, key):
        # type: (Text, Text) -> Optional[Text]
        pass

    @typing.overload
    def _get(self, section_id, key, default):
        # type: (Text, Text, Text) -> Text
        pass

    def _get(self, section_id, key, default=None):
        # type: (Text, Text, Optional[Text]) -> Optional[Text]
        if self.parser.has_option(section_id, key):
            return self.parser.get(section_id, key)
        return default

    def run_all(self):
        # type: () -> None
        """Run all the jobs specified in the configuration file.
        """
        logger.debug("Creating batch session")
        self.session = Session()

        for section_id in self.parser.sections():
            self.run_job(section_id)

    def run_job(self, section_id):
        # type: (Text, Optional[Session]) -> None
        """Run a job as described in the section named ``section_id``.

        Raises:
            KeyError: when the section could not be found.

        """
        if not self.parser.has_section(section_id):
            raise KeyError('section not found: {}'.format(section_id))

        self.session = self.session or Session()
        self.rotatecmd=self._get(section_id, 'rotatecmd', None)
        self.rotateip=int(self._get(section_id, 'rotateip', 0))
        self.rotation=1

        for name, looter_cls in six.iteritems(self._CLS_MAP):

                targets = self.get_targets(self._get(section_id, name),section_id)
                quiet = self._getboolean(
                    section_id, "quiet", self.args.get("--quiet", False))

                if targets:
                    logger.info("Launching {} job for section {}".format(name, section_id))

                for target, directory in six.iteritems(targets):
                    try:
                        logger.info("Downloading {} to {}".format(target, directory))
                        cmd=self.rotatecmd
                        noposts=self._get(section_id, 'noposts', False)
                        if self.rotatecmd is not None:
                          if noposts:
                            cmd=None
                            if self.rotation > 0:
                              self.rotation = self.rotation-1
                              if self.rotation < 1:
                                self.rotation = self.rotateip
                                cmd = self.rotatecmd
                            
                        looter = looter_cls(
                            target,
                            add_metadata=self._getboolean(section_id, 'add-metadata', False),
                            get_videos=self._getboolean(section_id, 'get-videos', False),
                            videos_only=self._getboolean(section_id, 'videos-only', False),
                            jobs=self._getint(section_id, 'jobs', 1),
                            template=self._get(section_id, 'template', '{id}'),
                            csvfilename=self._get(section_id, 'csv', None),
                            profilecsv=self._get(section_id, 'profilecsv', None),
                            noposts=self._get(section_id, 'noposts', False),
                            rotatecmd=cmd,
                            rotateip=self._get(section_id, 'rotateip', 0),
                            dump_json=self._getboolean(section_id, 'dump-json', False),
                            dump_only=self._getboolean(section_id, 'dump-only', False),
                            session=self.session)

                        self.session=looter.session

                        if self.parser.has_option(section_id, 'username'):
                            looter.logout()
                            username = self._get(section_id, 'username')
                            password = self._get(section_id, 'password') or \
                                getpass.getpass('Password for "{}": '.format(username))
                            looter.login(username, password)

                        timeframe=self._get(section_id, 'timeframe');
                        if timeframe is not None:
                            timeframe=get_times_from_cli(timeframe)

                        n = looter.download(
                            directory,
                            media_count=self._getint(section_id, 'num-to-dl'),
                            new_only=self._getboolean(section_id, 'new', False),
                            timeframe=timeframe,
                            pgpbar_cls=None if quiet else TqdmProgressBar,
                            dlpbar_cls=None if quiet else TqdmProgressBar)

                        logger.success("Downloaded %i medias !", n)

                    except Exception as exception:
                        logger.error(six.text_type(exception))
                        if self._getboolean(section_id, 'traceback', False):
                          traceback.print_exc()


    def get_targets(self, raw_string,section_id):
        # type: (Optional[Text]) -> Dict[Text, Text]
        """Extract targets from a string in 'key: value' format.
        """
        targets = {}
        if raw_string is not None:
            for line in raw_string.splitlines():
                if line:
                  target=""
                  directory="."
                  try:
                    target, directory = line.split(':', 1)
                  except:
                    target=line
                    directory=self._get(section_id, 'directory',".")
                  finally:
                    targets[target.strip()] = directory.strip()
        return targets
