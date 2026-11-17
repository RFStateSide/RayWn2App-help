#!/usr/bin/env python3
# Copyright (C) 2026 RF StateSide LLC; SPDX-License-Identifier: LGPL-3.0-only
"""Standard-library API v1 consumer. No embedded station credentials."""
import argparse,csv,getpass,hashlib,hmac,http.client,json,math,os,re,ssl,sys,tempfile,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode,urlsplit

class ApiError(Exception):pass

class StationApi:
    def __init__(self,base_url,token,ca=None,fingerprint=None,timeout=5):
        url=urlsplit(base_url)
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('','/'):
            raise ApiError('Use an HTTPS origin such as https://station.example:47828 without credentials, query or path.')
        if not re.fullmatch(r'[a-f0-9]{64}',token):raise ApiError('Supply the opaque API token through RAYWN2_API_TOKEN or the private prompt.')
        try:port=url.port or 443
        except ValueError:raise ApiError("Invalid HTTPS port.") from None
        self.host=url.hostname;self.port=port;self.token=token;self.timeout=timeout
        self.context=ssl.create_default_context(cafile=ca or None)
        self.pin=(fingerprint or '').replace(':','').lower()
        if self.pin:
            if not re.fullmatch(r'[a-f0-9]{64}',self.pin):raise ApiError('Fingerprint must be a SHA-256 certificate digest.')
            # An existing WSS certificate may lack an IP SAN. Keep chain/date verification
            # enabled and verify the independently obtained exact pin before sending a token.
            self.context.check_hostname=False
    def get(self,path,query=None):
        if path not in ('status','devices','readings','history/segments','history/page'):raise ApiError('Unknown read-only endpoint.')
        target='/api/v1/'+path+('?' + urlencode(query) if query else '')
        conn=http.client.HTTPSConnection(self.host,self.port,context=self.context,timeout=self.timeout)
        try:
            conn.connect()
            if self.pin and not hmac.compare_digest(hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest(),self.pin):
                raise ApiError('Certificate fingerprint changed. Verify the host identity locally.')
            conn.request('GET',target,headers={'Authorization':'Bearer '+self.token,'Accept':'application/json'})
            response=conn.getresponse();raw=response.read(256*1024+1)
            if len(raw)>256*1024:raise ApiError('Response exceeded the API size limit.')
            # http.client never follows redirects, so it cannot forward the token to another host.
            if response.status!=200:raise ApiError('API returned HTTP '+str(response.status)+'. Check grants, TLS, query and history availability.')
            if response.getheader('Content-Type','').split(';')[0].strip()!='application/json':raise ApiError('Expected an API JSON response.')
            result=json.loads(raw)
            if not isinstance(result,dict) or result.get('schema')!=1:raise ApiError('Unsupported response schema.')
            return result
        except (OSError,ValueError,http.client.HTTPException) as error:
            raise ApiError('HTTPS request failed ('+type(error).__name__+'). Check station availability and certificate trust.') from None
        finally:conn.close()

def channel_view(payload,identity,channel):
    empty={'device':identity,'channel':channel,'available':False,'received_utc':None,'expires_after_ms':0,
        'forward_average_W':None,'forward_peak_W':None,'reflected_average_W':None,'reflected_peak_W':None,'swr':None}
    device=next((d for d in payload.get('devices',[]) if d.get('device')==identity),None)
    if not device:return {**empty,'status':'Device not returned'}
    age=device.get('age_ms',-1)
    rf=next((c for c in device.get('rf',[]) if c.get('channel')==channel),None)
    if device.get('fresh') is not True or not isinstance(age,(int,float)) or isinstance(age,bool) or not 0<=age<1500 or not rf:
        return {**empty,'status':'Unavailable / stale'}
    return {**empty,'available':True,'source':device.get('source'),'transport':device.get('transport'),
        'received_utc':device.get('received_utc'),'expires_after_ms':int(1500-age),'status':rf.get('status',''),
        **{k:rf.get(k) if isinstance(rf.get(k),(int,float)) and not isinstance(rf.get(k),bool) and math.isfinite(rf[k]) else None
           for k in ('forward_average_W','forward_peak_W','reflected_average_W','reflected_peak_W','swr')}}

def safe_cell(value):
    text=value.lstrip()
    if text[:1] in ('=','+','-','@'):
        try:float(text)
        except ValueError:return "'"+value
    return value

def export_segment(api,identity,segment,channel,destination,overwrite=False):
    destination=Path(destination)
    if destination.exists() and not overwrite:raise ApiError('Output already exists. Choose another file or use --overwrite.')
    name=None;offset=end=0;columns=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',newline='',encoding='utf-8',prefix='.raywn2-',suffix='.partial',dir=destination.parent,delete=False) as output:
            name=output.name;writer=csv.writer(output)
            for _ in range(32768):
                page=api.get('history/page',{'device':identity,'segment':segment,'channel':channel,'offset':offset,'end':end})
                current=page['columns'];next_offset=page['next'];boundary=page['end']
                if not isinstance(next_offset,int) or not isinstance(boundary,int) or not 0<=next_offset<=boundary<=2097152:raise ApiError('Invalid history cursor.')
                if columns is None:columns=current;end=boundary;writer.writerow(columns)
                if columns!=current or end!=boundary:raise ApiError('History changed during export. Refresh the segment list.')
                for row in page['rows']:
                    if len(row)!=len(columns) or not all(isinstance(c,str) for c in row):raise ApiError('Invalid history row.')
                    record=dict(zip(columns,row))
                    if record.get('device')!=identity or channel and record.get('channel')!=str(channel):raise ApiError('Unexpected history source.')
                    writer.writerow([safe_cell(cell) for cell in row])
                if page['more'] is False:break
                if next_offset<=offset:raise ApiError('History cursor did not advance.')
                offset=next_offset
            else:raise ApiError('History page limit reached.')
            output.flush();os.fsync(output.fileno())
        if destination.exists() and not overwrite:raise ApiError('Output appeared during export. Choose another file.')
        if overwrite:os.replace(name,destination)
        else:
            try:os.link(name,destination)
            except FileExistsError:raise ApiError("Output appeared during export. Choose another file.") from None
            os.unlink(name)
        name=None
    except (KeyError,TypeError,ValueError) as error:raise ApiError('Invalid history response ('+type(error).__name__+').') from None
    finally:
        if name:
            try:os.unlink(name)
            except FileNotFoundError:pass

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default=os.getenv('RAYWN2_API_URL',''))
    parser.add_argument('--ca',default=os.getenv('RAYWN2_API_CA'))
    parser.add_argument('--fingerprint',default=os.getenv('RAYWN2_API_FINGERPRINT'))
    parser.add_argument('--device',default=os.getenv('RAYWN2_API_DEVICE',''))
    parser.add_argument('--channel',type=int,choices=range(1,5),default=2)
    sub=parser.add_subparsers(dest='action',required=True)
    for action in ('status','devices','readings','segments'):sub.add_parser(action)
    watch=sub.add_parser('watch');watch.add_argument('--count',type=int,default=0)
    export=sub.add_parser('export');export.add_argument('--segment',required=True);export.add_argument('--output',required=True);export.add_argument('--all-channels',action='store_true');export.add_argument('--overwrite',action='store_true')
    args=parser.parse_args()
    if args.action in ('watch','segments','export') and not args.device:parser.error('--device or RAYWN2_API_DEVICE is required')
    token=os.getenv('RAYWN2_API_TOKEN')
    if not token:
        if not sys.stdin.isatty():parser.error('Set RAYWN2_API_TOKEN for noninteractive use')
        token=getpass.getpass('Station API token (not displayed): ')
    try:
        api=StationApi(args.base_url,token,args.ca,args.fingerprint)
        if args.action=='watch':
            count=0
            while args.count<=0 or count<args.count:
                try:result=channel_view(api.get('readings',{'device':args.device}),args.device,args.channel)
                except ApiError:result=channel_view({},args.device,args.channel);result['status']='HTTPS failed; readings cleared'
                result['observed_utc']=datetime.now(timezone.utc).isoformat();print(json.dumps(result,ensure_ascii=False),flush=True)
                count+=1
                if args.count<=0 or count<args.count:time.sleep(1)
        elif args.action=='export':export_segment(api,args.device,args.segment,0 if args.all_channels else args.channel,args.output,args.overwrite);print('Saved selected history to '+args.output)
        else:
            path='history/segments' if args.action=='segments' else args.action
            query={'device':args.device} if args.device and args.action in ('segments','readings') else None
            print(json.dumps(api.get(path,query),indent=2,ensure_ascii=False))
        return 0
    except ApiError as error:print(str(error),file=sys.stderr);return 1
    except OSError as error:print("Local file/network operation failed ("+type(error).__name__+"). Check CA and output paths.",file=sys.stderr);return 1
    except KeyboardInterrupt:return 0

if __name__=='__main__':sys.exit(main())
