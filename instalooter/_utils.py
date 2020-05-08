# coding: utf-8
"""Internal utility classes and functions.
"""
from __future__ import absolute_import
from __future__ import unicode_literals

import datetime
import hashlib
import operator
import os
import re
import typing
import csv
import time

import six

from ._impl import json

if typing.TYPE_CHECKING:
    from typing import Any, Dict, Mapping, Optional, Text


class NameGenerator(object):
    """Generator for filenames using a template.
    """
    writer=None

    @classmethod
    def _get_info(cls, media):
        # type: (Mapping[Text, Any]) -> Mapping[Text, Any]

        info = {
            'id': media['id'],
            'code': media['shortcode'],
            'ownerid': media['owner']['id'],
            'username': media['owner'].get('username'),
            'fullname': media['owner'].get('full_name'),
            'commentscount': 0,
            'hashtags': 0,
            'likescount': media.get('edge_media_preview_like', {}).get('count'),
            'isad': media['is_ad'],
            'isvideo': media['is_video'],
#            'width': media.get('dimensions', {}).get('width'),
#            'height': media.get('dimensions', {}).get('height'),
        }  # type: Dict[Text, Any]

        commentscount=0
        try:
            comments=media.get('edge_media_preview_comment', {})
            if comments is not None:
                commentscount=comments.get('count') or 0
        except:
            commentscount=0                   
        info['commentscount']=commentscount

        hashtags=0
        try:
            caption=media.get('edge_media_to_caption', {})
            if caption is not None:
                edges=caption.get('edges', [])
                if edges is not None:
                    text=edges[0].get('node').get('text')
                    hashtags=text.count('#')
        except:
            hashtags=0                   
        info['hashtags']=hashtags

        timestamp = media.get('date') or media.get('taken_at_timestamp')
        if timestamp is not None:
            dt = datetime.datetime.fromtimestamp(timestamp)
#            info['datetime'] = ("{0.year}-{0.month:02d}-{0.day:02d} {0.hour:02d}"
#                "h{0.minute:02d}m{0.second:02d}s{0.microsecond}").format(dt)
            info['year'] = ("{0.year}").format(dt)
            info['month'] = ("{0.month:02d}").format(dt)
            info['day'] = ("{0.day:02d}").format(dt)
#            info['date'] = datetime.date.fromtimestamp(timestamp)

        
        return info
        #return dict(six.moves.filter(
        #    operator.itemgetter(1), six.iteritems(info)))

    def __init__(self, template="{id}",dump_csv=False, csvfilename="data"):
        # type: (Text) -> None
        self.template = template
        self.dump_csv=dump_csv
        if (dump_csv):
            if (NameGenerator.writer is None):
                self.csvfilename=csvfilename+".csv"
                NameGenerator.csvfile=open(self.csvfilename, mode='w')
                self.fieldnames = ['id','code','ownerid','username','fullname','commentscount','likescount','hashtags','isvideo','isad','year','month','day']
                NameGenerator.writer = csv.DictWriter(NameGenerator.csvfile, fieldnames=self.fieldnames)
                NameGenerator.writer.writeheader()

    def base(self, media):
        # type: (Mapping[Text, Any]) -> Text
        info = self._get_info(media)
        if (self.dump_csv):
          NameGenerator.writer.writerow(info)        
          NameGenerator.csvfile.flush()        
        return self.template.format(**info)

    def file(self, media, ext=None):
        # type: (Mapping[Text, Any], Optional[Text]) -> Text
        ext = ext or ("mp4" if media['is_video'] else "jpg")
        return os.path.extsep.join([self.base(media), ext])

    def needs_extended(self, media):
        # type: (Mapping[Text, Any]) -> bool
        try:
            self.base(media)
            return False
        except KeyError:
            return True


class CachedClassProperty(object):

    def __init__(self, factory):
        if not isinstance(factory, (classmethod, staticmethod)):
            factory = classmethod(factory)
        self.factory = factory
        self.value = self.sentinel = object()

    def __get__(self, obj, klass=None):
        if self.value is self.sentinel:
            self.value = self.factory.__get__(obj, klass)()
        return self.value

    def __set__(self, obj, value):
        raise AttributeError("can't set attribute")


def get_shared_data(html):
    match = re.search(r'window._sharedData = ({[^\n]*});', html)
    return json.loads(match.group(1))


def get_additional_data(html):
    match = re.search(r"window.__additionalDataLoaded\('/p/.*/',({[^\n]*})\);", html)
    return json.loads(match.group(1))
