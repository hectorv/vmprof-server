# -*- coding: utf-8 -*-
import json
import urllib
import hashlib
import tempfile
import os

from django.conf.urls import url, include
from django.contrib import auth
from django.http.response import HttpResponseBadRequest
from django.http import Http404
from django.shortcuts import get_object_or_404

from log.models import BinaryJitLog, get_reader
from vmprofile.models import Log
from vmprof.log.parser import _parse_jitlog


from rest_framework import views
from rest_framework.response import Response
from rest_framework.parsers import FileUploadParser
from rest_framework import permissions
from rest_framework.serializers import BaseSerializer
from rest_framework import viewsets

def compute_checksum(file_obj):
    hash = hashlib.md5()
    for chunk in file_obj.chunks():
        hash.update(chunk)
    return hash.hexdigest()

class BinaryJitLogFileUploadView(views.APIView):
    parser_classes = (FileUploadParser,)
    permission_classes = (permissions.AllowAny,)

    def post(self, request, profile, format=None):
        file_obj = request.FILES['file']

        filename = file_obj.name
        if not filename.endswith('.bz2') and \
           not filename.endswith('.xz'):
            return HttpResponseBadRequest("must be either bzip2 or lzma compressed")

        checksum = compute_checksum(file_obj)

        user = request.user if request.user.is_authenticated() else None

        profile_obj = Log.objects.get(checksum=profile)
        log, _ = BinaryJitLog.objects.get_or_create(file=file_obj, checksum=checksum,
                                                    user=user, profile=profile_obj)

        return Response(log.checksum)

class LogMetaSerializer(BaseSerializer):
    def to_representation(self, jlog):
        forest = jlog.decode_forest()
        traces = {}
        for id, trace in forest.traces.items():
            mp = trace.get_first_merge_point()
            mp_meta = { 'scope': 'unknown', 'lineno': -1, 'filename': '',
                        'type': trace.type }
            traces[id] = mp_meta
            if mp:
                mp_meta['scope'] = mp.get_scope()
                lineno, filename = mp.get_source_line()
                mp_meta['lineno'] = lineno
                mp_meta['filename'] = filename
        #
        return {
            'resops': forest.resops,
            'traces': traces
        }

class MetaForestViewSet(viewsets.ModelViewSet):
    queryset = BinaryJitLog.objects.all()
    serializer_class = LogMetaSerializer
    permission_classes = (permissions.AllowAny,)

def get_forest_for(jlog):
    return jlog.decode_forest()

class TraceSerializer(BaseSerializer):
    def to_representation(self, trace):
        return str(trace)


class TraceViewSet(viewsets.ModelViewSet):
    queryset = BinaryJitLog.objects.all()
    permission_classes = (permissions.AllowAny,)
    serializer_class = TraceSerializer

    def get_object(self):
        if 'id' not in self.request.GET:
            raise Http404("mandatory id GET parameter missing")
        id = int(self.request.GET['id'], 16)
        queryset = self.get_queryset()
        filter = {}
        obj = get_object_or_404(queryset, **filter)
        self.check_object_permissions(self.request, obj)
        forest = get_forest_for(obj)
        trace = forest.get_trace_by_id(id)
        return trace
