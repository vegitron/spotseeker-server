from spotseeker_server.views.rest_dispatch import RESTDispatch
from spotseeker_server.forms.spot_search import SpotSearchForm
from spotseeker_server.views.spot import SpotView
from django.http import HttpResponse
from spotseeker_server.require_auth import *
from spotseeker_server.models import Spot
from pyproj import Geod
from decimal import *
import simplejson as json
import re
from time import *
from datetime import datetime
import sys


class SearchView(RESTDispatch):
    """ Handles searching for Spots with particular attributes based on a query string.
    """
    @user_auth_required
    def POST(self, request):
        return SpotView().run(request)

    @app_auth_required
    def GET(self, request):
        form = SpotSearchForm(request.GET)
        has_valid_search_param = False

        if not form.is_valid():
            return HttpResponse('[]')

        if len(request.GET) == 0:
            return HttpResponse('[]')

        query = Spot.objects.all()

        if 'distance' in request.GET and 'center_longitude' in request.GET and 'center_latitude' in request.GET:
            try:
                g = Geod(ellps='clrk66')
                top = g.fwd(request.GET['center_longitude'], request.GET['center_latitude'], 0, request.GET['distance'])
                right = g.fwd(request.GET['center_longitude'], request.GET['center_latitude'], 90, request.GET['distance'])
                bottom = g.fwd(request.GET['center_longitude'], request.GET['center_latitude'], 180, request.GET['distance'])
                left = g.fwd(request.GET['center_longitude'], request.GET['center_latitude'], 270, request.GET['distance'])

                top_limit = "%.8f" % top[1]
                bottom_limit = "%.8f" % bottom[1]
                left_limit = "%.8f" % left[0]
                right_limit = "%.8f" % right[0]

                query = query.filter(longitude__gte=left_limit)

                query = query.filter(longitude__lte=right_limit)
                query = query.filter(latitude__gte=bottom_limit)
                query = query.filter(latitude__lte=top_limit)
                has_valid_search_param = True
            except Exception as e:
                if not request.META['SERVER_NAME'] == 'testserver':
                    print >> sys.stderr, "E: ", e
                query = Spot.objects.all()

        day_dict = {"Sunday": "su",
                    "Monday": "m",
                    "Tuesday": "t",
                    "Wednesday": "w",
                    "Thursday": "th",
                    "Friday": "f",
                    "Saturday": "sa", }
        # Exclude things that get special consideration here, otherwise add a filter for the keys
        for key in request.GET:
            if re.search('^oauth_', key):
                pass
            elif key == "distance":
                pass
            elif key == "center_latitude":
                pass
            elif key == "center_longitude":
                pass
            elif key == "limit":
                pass
            elif key == "open_now":
                if request.GET["open_now"]:

                    day_lookup = ["su", "m", "t", "w", "th", "f", "sa"]
                    day_num = int(strftime("%w", localtime()))
                    today = day_lookup[day_num]
                    now = datetime.time(datetime.now())
                    query = query.filter(spotavailablehours__day__iexact=today, spotavailablehours__start_time__lt=now, spotavailablehours__end_time__gt=now)
                    has_valid_search_param = True
            elif key == "open_until":
                if request.GET["open_until"] and request.GET["open_at"]:
                    until_day, until_time = request.GET["open_until"].split(',')
                    at_day, at_time = request.GET["open_at"].split(',')
                    until_day = day_dict[until_day]
                    at_day = day_dict[at_day]

                    if until_day == at_day:
                        query = query.filter(spotavailablehours__day__iexact=until_day, spotavailablehours__start_time__lte=at_time, spotavailablehours__end_time__gte=until_time)
                    else:
                        days_to_test = self.get_days_in_range(at_day, until_day)
                        last_day = days_to_test.pop()
                        days_to_test.reverse()
                        first_day = days_to_test.pop()

                        query = query.filter(spotavailablehours__day__iexact=first_day, spotavailablehours__start_time__lte=at_time, spotavailablehours__end_time__gte="23:59")
                        query = query.filter(spotavailablehours__day__iexact=last_day, spotavailablehours__start_time__lte="00:00", spotavailablehours__end_time__gte=until_time)

                        for day in days_to_test:
                            query = query.filter(spotavailablehours__day__iexact=day, spotavailablehours__start_time__lte="00:00", spotavailablehours__end_time__gte="23:59")
                    has_valid_search_param = True
            elif key == "open_at":
                if request.GET["open_at"]:
                    try:
                        request.GET["open_until"]
                    except:
                        day, time = request.GET['open_at'].split(',')
                        day = day_dict[day]
                        query = query.filter(spotavailablehours__day__iexact=day, spotavailablehours__start_time__lte=time, spotavailablehours__end_time__gte=time)
                        has_valid_search_param = True
            elif re.search('^extended_info:', key):
                kwargs = {
                   'spotextendedinfo__key': key[14:],
                   'spotextendedinfo__value__in': request.GET.getlist(key)
                }
                query = query.filter(**kwargs)
                has_valid_search_param = True
            elif key == "id":
                query = query.filter(id__in=request.GET.getlist(key))
                has_valid_search_param = True
            else:
                try:
                    kwargs = {
                        '%s__icontains' % key: request.GET[key]
                    }
                    query = query.filter(**kwargs)
                    has_valid_search_param = True
                except Exception as e:
                    if not request.META['SERVER_NAME'] == 'testserver':
                        print >> sys.stderr, "E: ", e

        if not has_valid_search_param:
            return HttpResponse('[]')

        limit = 20
        if 'limit' in request.GET:
            if request.GET['limit'] == '0':
                limit = 0
            else:
                limit = int(request.GET['limit'])

        if limit > 0 and limit < len(query):
            sorted_list = list(query)
            sorted_list.sort(lambda x, y: cmp(self.distance(x, request.GET['center_longitude'], request.GET['center_latitude']), self.distance(y, request.GET['center_longitude'], request.GET['center_latitude'])))
            query = sorted_list[:limit]

        response = []

        for spot in query:
            response.append(spot.json_data_structure())

        return HttpResponse(json.dumps(response))

    def distance(self, spot, longitude, latitude):
        g = Geod(ellps='clrk66')
        az12, az21, dist = g.inv(spot.longitude, spot.latitude, longitude, latitude)
        return dist


    def get_days_in_range(self, start_day, until_day):
        day_lookup = ["su", "m", "t", "w", "th", "f", "sa", "su", "m", "t", "w", "th", "f", "sa"]
        matched_days = []
        add_days = False

        for day in day_lookup:
            if day == start_day:
                add_days = True
            if add_days:
                matched_days.append(day)

            if day == until_day and add_days == True:
                return matched_days

        return []
