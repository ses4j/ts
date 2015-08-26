import logging, re, os, shutil
from datetime import datetime

from modgrammar import *
from dateutil.parser import parse as dateutil_parse

def samefile(f1, f2):
    '''
    A simple replacement of the os.path.samefile() function not existing 
    on the Windows platform. 
    MAC/Unix supported in standard way :).

    Author: Denis Barmenkov <denis.barmenkov@gmail.com>

    Source: code.activestate.com/recipes/576886/

    Copyright: this code is free, but if you want to use it, please
               keep this multiline comment along with function source. 
               Thank you.

    2009-08-19 20:13 
    '''
    try:
        return os.path.samefile(f1, f2)
    except AttributeError:
        f1 = os.path.abspath(f1).lower()
        f2 = os.path.abspath(f2).lower()
        return f1 == f2



logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

grammar_whitespace = False

class MyDate(Grammar):
    grammar = (WORD('0-9', "0-9/", grammar_name='date'))
    grammar_tags = ['date']

class Hours (Grammar):
    grammar = (WORD(".0-9", grammar_name='hours'), OPTIONAL("h"))

class Hour(Grammar):
    grammar = WORD("0-9", min=1, max=2, grammar_name='hour')

class Minute(Grammar):
    grammar = WORD("0-9", min=1, max=2, grammar_name='minute')    

class AMPM(Grammar):
    grammar = L("A") | L("P") | L("a") | L("p")

class MyTime (Grammar):
    grammar = (G(Hour, OPTIONAL(":", Minute))), OPTIONAL(AMPM)
    # grammar = (WORD("0-9:", grammar_name='time'), OPTIONAL(L("A") | L("P") | L("a") | L("p"), grammar_name='ampm'))

class Range (Grammar):
    grammar = G(MyTime, OPTIONAL(SPACE), '-', OPTIONAL(SPACE),
        OPTIONAL(MyTime), OPTIONAL('(', Hours, ')'), grammar_name='range')

class RangeList(Grammar):
    grammar = LIST_OF(G(Range | Hours), sep=G(",", OPTIONAL(SPACE)), grammar_name="ranges")

class Prefix(Grammar):
    grammar = (ZERO_OR_MORE(L('*') | SPACE), )

class Suffix(Grammar):
    grammar = (OPTIONAL(SPACE), OPTIONAL(L('#'), REST_OF_LINE), EOF)

class MyGrammar (Grammar):

    grammar = (
        G(Prefix, MyDate, SPACE, Hours, SPACE, RangeList, Suffix, grammar_name="3args") |
        G(Prefix, MyDate, SPACE, RangeList,  Suffix, grammar_name="2argrange") |
        G(Prefix, MyDate, SPACE, Hours, Suffix, grammar_name="2arghours") |  
        G(Prefix, MyDate, Suffix, grammar_name="justdate")
    )

myparser = MyGrammar.parser()

time_regex = re.compile(r'(\d{1,2})(:\d+)?([aApP])?')
def parse_time(cur_date, time_str, after=None):
    """ Parse time 

    >>> parse_time(datetime(2015, 6, 3, 0, 0), '1')
    datetime.datetime(2015, 6, 3, 13, 0)
    >>> parse_time(datetime(2015, 6, 3, 0, 0), '1a')
    datetime.datetime(2015, 6, 3, 1, 0)
    >>> parse_time(datetime(2015, 6, 3, 0, 0), '11:45p')
    datetime.datetime(2015, 6, 3, 23, 45)
    >>> parse_time(datetime(2015, 6, 3, 0, 0), '12:45a')
    datetime.datetime(2015, 6, 3, 0, 45)
    >>> parse_time(datetime(2015, 6, 3, 0, 0), '12:45p')
    datetime.datetime(2015, 6, 3, 12, 45)
    """

    m = time_regex.match(time_str)
    # print( "[parse_time]: " + time_str, m.groups())
    if not m:
        return None

    g = m.groups()
    # print(g)
    hour = int(g[0])
    minute = 0
    if g[1] is not None:
        minute = int(g[1][1:])
    
    if g[2] is not None:
        if hour != 12 and g[2] in ('p','P'):
            hour += 12
        elif hour == 12 and g[2] in ('a','A'):
            hour -= 12
    else:
        # AM/PM not specified.
        ret = cur_date.replace(hour=hour, minute=minute)
        if after is not None:
            if after > ret:
                hour += 12
        else:
            if hour < 7:
                logger.warn("Assuming time {} is PM".format(time_str))
                hour += 12

    return cur_date.replace(hour=hour, minute=minute)

class TimesheetParseError(Exception):
    pass

def parse(line, prefix='* '):
    """ Parse grammar.
    >>> myparser.parse_string("5/20/2015", reset=True, eof=True)
    MyGrammar<'5/20/2015'>
    >>> parse("5/20/2015", prefix='')
    {'date': datetime.datetime(2015, 5, 20, 0, 0), 'prefix': Prefix<''>, 'suffix': Suffix<None, None, ''>}
    >>> d = parse("6/21/2015 1.25  3:33-4:44a", prefix='')
    Traceback (most recent call last):
        ...
    TimesheetParseError: huh?
    >>> d = parse("5/20/2015 5  10:10 - 10:25a, 12-", prefix='')
    >>> d['date']
    datetime.datetime(2015, 5, 20, 0, 0)
    >>> d['hours']
    0.25
    >>> len(d['ranges'])
    2
    >>> d['ranges'][0]['s']
    datetime.datetime(2015, 5, 20, 10, 10)
    >>> format_ret(d)
    '2015-05-20   .25 10:10a-10:25a(.25),12a-'
    >>> d = parse('6/15/2015 4.25  10a-11:30(1.5), 3-5:45p(2.75)', prefix='')
    >>> d['ranges'][1]['duration']
    2.75
    >>> d = parse('* 6/3/2015  1.5  10a-11:15a, 12:45p-1p, 6-6:15 # whatever yo', prefix='* ')
    >>> d = parse('* 7/22/2015 6.25  10:00a-11:30a(1.5), 12:30p-3:30p(3), 9:15p-11p(1.75)', prefix='* ')
    >>> d = parse('* 7/13/2015 3.5  .25, 1:30p-5p', prefix='* ')
    >>> format_ret(d)
    '* 2015-07-13  3.75 .25,1:30p-5p(3.50)'
    """
    
    if not line.strip():
        return None

    origresult = myparser.parse_string(line.rstrip(), reset=True, eof=True) #, matchtype='longest')
    ret = {}
    result = origresult.elements[0]

    date_g = result.get(MyDate)
    if date_g is None:
        return None

    ret['prefix'] = result.get(Prefix)
    ret['suffix'] = result.get(Suffix)

    cur_date = dateutil_parse(str(date_g))
    ret['date'] = cur_date
    
    hours_g = result.get(Hours)
    if hours_g is not None:
        ret['hours'] = float(str(hours_g))
    
    ranges = result.get(RangeList)
    if ranges is not None:
        ret['ranges'] = []
        # logger.debug(ranges.elements)

        for r in ranges.elements[0].elements:
            if r.grammar_name == 'Hours':
                duration = float(str(r))
                ret['ranges'].append( {'duration': duration} )
            elif r.grammar_name == 'Range':
                times = r.find_all(MyTime)
                if len(times)==1:
                    start = str(times[0])
                    end = None
                elif len(times)==2:
                    start = str(times[0])
                    end = str(times[1])
                else:
                    raise Exception()
                
                try:
                    parsed_start = parse_time(cur_date, start)
                except (ValueError, ):
                    parsed_start = None


                parsed_end = None
                if end is not None:
                    try:
                        parsed_end = parse_time(cur_date, end, after=parsed_start)
                    except (ValueError, AttributeError):
                        pass

                if parsed_end is not None:
                    if parsed_end < parsed_start:
                        raise TimesheetParseError("huh?")
                    duration = (parsed_end-parsed_start).seconds/60./60.
                else:
                    duration = None
                ret['ranges'].append( {'s': parsed_start, 'e': parsed_end, 'duration': duration} )
            else:
                pass

    
    if 'ranges' in ret:
        total_duration = sum([r['duration'] for r in ret['ranges'] if r['duration'] is not None])
        if 'hours' in ret and total_duration != ret['hours']:
            logger.warn('changing total hours from %s to %s' % (ret['hours'], total_duration))
        ret['hours'] = total_duration

        if len(ret['ranges']) == 1 and 's' not in ret['ranges'][0]:
            del ret['ranges']


    # logger.debug('line={}\n-> ret={}'.format(line, ret))

    return ret

def format_hours(h):
    if h is None:
        return '-'
    if int(h) == h:
        return str(int(h))

    return ("%.2f" % h).lstrip('0')

def format_range(r,):
    def format_time(t):
        if t is None:
            return ""

        ampm = "a"
        if t.hour > 12 or (t.hour == 12 and t.minute > 0):
            ampm = "p"
            hour = t.hour - 12
        else:
            hour = t.hour

        if t.minute==0:
            s = "%d%s" % (hour, ampm)
        else:
            s = "%d:%2d%s" % (hour, t.minute, ampm)
        return s
    if 's' not in r:
        return '%s' % format_hours(r['duration'])
    else:
        if r['e'] is not None:
            return "%s-%s(%s)" % (format_time(r['s']), format_time(r['e']), format_hours(r['duration']))
        else:
            return "%s-" % (format_time(r['s']), )

def format_ret(ret):
    if 'ranges' not in ret:
        total_duration = ret['hours']
        output = '%10s %5s' % (ret['date'].date(), format_hours(total_duration))
    else:
        parsed_ranges = ret['ranges']
        rearranges = [format_range(r) for r in parsed_ranges]
        output = '%10s %5s %s' % (ret['date'].date(), format_hours(ret['hours']), ", ".join(rearranges))

    return '%s%s%s' % (ret['prefix'], output, str(ret['suffix']).rstrip())


if __name__=='__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Process a timesheet')
    parser.add_argument('-f', '--file', required=True)
    parser.add_argument('-o', '--out', default=None)

    args = parser.parse_args()
    f = open(args.file)

    if args.out is not None:
        if samefile(args.file, args.out):
            f.close()
            backup_filename = args.file + '.backup'
            shutil.copyfile(args.file, backup_filename)
            f = open(backup_filename)

        outf = open(args.out, 'w')
    else:
        outf = None

    for line in f:
        print line.rstrip()
        try:
            ret = parse(line)
            if ret is None:
                if outf:
                    outf.write(line.rstrip() + '\n')
                continue

            fixed_line = format_ret(ret)
            print "+", fixed_line
            if outf:
                outf.write(fixed_line.rstrip() + '\n')


        except TimesheetParseError:
            raise
        except ParseError:
            if outf:
                outf.write(line.rstrip() + '\n')

            # print 'skipped...'
            pass
            # logger.exception("failed to parse")
            # raise
