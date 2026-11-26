"""60-second exhibition game, for DoYouLikeFlowers HIL code. Default: no hardware."""
import argparse, json, math, queue, secrets, socket, threading, time, sys, sqlite3, os, csv, io, re
from concurrent.futures import Future, CancelledError, TimeoutError as FutureTimeout
from urllib.parse import urlsplit
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
DURATION = 60.0
BUTTON = {'start':16,'back':32,'rb':512}
AXES = ('lx','ly','rx','ry','lt','rt')
MOTORS = ['shoulder_pan','shoulder_lift','elbow_flex','wrist_flex','wrist_roll','gripper']

class Pad:
    def __init__(self, port):
        self.lock = threading.Lock(); self.state = None; self.stamp = 0
        self.server = socket.socket(); self.server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        self.server.bind(('127.0.0.1',port)); self.server.listen(1)
        threading.Thread(target=self.run,daemon=True).start()
    def clear(self):
        with self.lock: self.state = None
    def run(self):
        while True:
            try: conn,_ = self.server.accept()
            except OSError: return
            self.clear()
            with conn:
                conn.settimeout(.25); buf=b''
                try:
                    while True:
                        data=conn.recv(4096)
                        if not data: break
                        buf+=data
                        if len(buf)>32768: break
                        while b'\n' in buf:
                            line,buf=buf.split(b'\n',1)
                            s=json.loads(line)
                            if s.get('pad',-1)<0: self.clear(); continue
                            if not all(k in s and isinstance(s[k],(int,float)) and math.isfinite(s[k]) and abs(s[k])<=1.01 for k in AXES): raise ValueError('bad axes')
                            if not isinstance(s.get('btn'),int) or not 0<=s['btn']<=65535: raise ValueError('bad buttons')
                            with self.lock: self.state=s; self.stamp=time.monotonic()
                except (OSError,ValueError,TypeError,AttributeError): pass
                finally: self.clear()
    def get(self):
        with self.lock: return dict(self.state) if self.state and time.monotonic()-self.stamp<.20 else None

COUNTDOWN = 3.65
ACTIVE = ('COUNTDOWN', 'PLAY')

def identity(contact):
    # No-contact participants cannot be reliably linked across attempts.
    if not contact: return 'guest:'+secrets.token_hex(16)
    c=contact.strip().casefold()
    if re.fullmatch(r'[+\d\s().-]+',c): c=re.sub(r'\D','',c) or c
    return 'contact:'+c

class Records:
    """Local-only DB. Contact information never enters public status."""
    def __init__(self, path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600); os.close(fd)
        self.db = sqlite3.connect(self.path)
        self.db.execute("CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, nickname TEXT NOT NULL, contact TEXT NOT NULL, result TEXT NOT NULL DEFAULT 'IN_PROGRESS', ms INTEGER, created TEXT DEFAULT CURRENT_TIMESTAMP, day INTEGER NOT NULL DEFAULT 1, participant_key TEXT NOT NULL DEFAULT '')")
        cols={row[1] for row in self.db.execute('PRAGMA table_info(runs)')}
        if not {'day','participant_key'}<=cols:
            # Preserve the pre-V3 database before assigning old records to day 1.
            backup=self.path.with_name(self.path.name+'.v2-backup-'+secrets.token_hex(4))
            fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            with sqlite3.connect(backup) as target: self.db.backup(target)
            print('V2 backup:',backup,flush=True)
        with self.db:
            if 'day' not in cols: self.db.execute('ALTER TABLE runs ADD COLUMN day INTEGER NOT NULL DEFAULT 1')
            if 'participant_key' not in cols: self.db.execute("ALTER TABLE runs ADD COLUMN participant_key TEXT NOT NULL DEFAULT ''")
            for rid,c in self.db.execute("SELECT id,contact FROM runs WHERE participant_key='' ").fetchall():
                self.db.execute('UPDATE runs SET participant_key=? WHERE id=?',(identity(c),rid))
            self.db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            self.db.execute("INSERT OR IGNORE INTO settings VALUES ('active_day','1')")
            self.db.execute("UPDATE runs SET result='STOP' WHERE result='IN_PROGRESS'")
        self.active_day=int(self.db.execute("SELECT value FROM settings WHERE key='active_day'").fetchone()[0])
    def set_day(self,day):
        if type(day) is not int or day not in (1,2): raise ValueError('1일차 또는 2일차를 선택해 주세요.')
        with self.db: self.db.execute("UPDATE settings SET value=? WHERE key='active_day'",(str(day),))
        self.active_day=day
    def enter(self, nickname, contact):
        with self.db:
            return self.db.execute('INSERT INTO runs(nickname,contact,day,participant_key) VALUES (?,?,?,?)',(nickname,contact,self.active_day,identity(contact))).lastrowid
    def finish(self, rid, phase, elapsed):
        with self.db:
            self.db.execute("UPDATE runs SET result=?,ms=? WHERE id=? AND result='IN_PROGRESS'",(phase,round(elapsed*1000),rid))
    @staticmethod
    def scope(day):
        if day=='all': return '1=1',()
        if type(day) is not int or day not in (1,2): raise ValueError('조회 일차가 올바르지 않습니다.')
        return 'day=?',(day,)
    def public(self,day='all'):
        where,params=self.scope(day)
        rows=self.db.execute(f"""WITH best AS (SELECT nickname,ms,id,ROW_NUMBER() OVER (PARTITION BY participant_key ORDER BY ms,id) AS rn FROM runs WHERE result='SUCCESS' AND ms IS NOT NULL AND {where}) SELECT nickname,ms FROM best WHERE rn=1 ORDER BY ms,id LIMIT 3""",params).fetchall()
        wins, attempts = self.db.execute(f"SELECT COUNT(CASE WHEN result='SUCCESS' THEN 1 END),COUNT(*) FROM runs WHERE {where}",params).fetchone()
        return [{'nickname':n,'ms':m} for n,m in rows], wins, attempts
    def boards(self):
        return {str(d):dict(zip(('ranking','wins','attempts'),self.public(d))) for d in (1,2,'all')}
    def list_runs(self,day,offset=0):
        where,params=self.scope(day)
        if type(offset) is not int or offset<0: raise ValueError('페이지 오류')
        count=self.db.execute(f'SELECT COUNT(*) FROM runs WHERE {where}',params).fetchone()[0]
        rows=self.db.execute(f'SELECT id,day,nickname,result,ms FROM runs WHERE {where} ORDER BY id DESC LIMIT 50 OFFSET ?',(*params,offset)).fetchall()
        return {'rows':[dict(zip(('id','day','nickname','result','ms'),r)) for r in rows],'total':count,'offset':offset}
    def delete(self,rid):
        if type(rid) is not int or rid<1: raise ValueError('기록 번호 오류')
        with self.db: return self.db.execute('DELETE FROM runs WHERE id=?',(rid,)).rowcount
    def clear(self,day):
        where,params=self.scope(day)
        with self.db: return self.db.execute(f'DELETE FROM runs WHERE {where}',params).rowcount
    def csv_text(self,day='all'):
        where,params=self.scope(day)
        def safe(v):
            return "'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v
        f=io.StringIO(newline='');w=csv.writer(f);w.writerow(['day','nickname','contact','result','elapsed_ms','created_utc'])
        for row in self.db.execute(f'SELECT day,nickname,contact,result,ms,created FROM runs WHERE {where} ORDER BY id',params): w.writerow([safe(v) for v in row])
        return '\ufeff'+f.getvalue()
    def export(self, path):
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w',encoding='utf-8',newline='') as f: f.write(self.csv_text())

# Screen-only rehearsal: no motor commands, no database entries.
# All directions refer to the mapped physical gamepad, as in the live guide.
PRACTICE_STEPS = (
    ('rb', 'R1', 'R1 버튼을 눌러 보세요', 'R1을 누르고 있어야 실제 로봇팔을 조작할 수 있어요.', '조작 허용', 'R1', 1),
    ('ls', '↑', 'R1 + 왼쪽 스틱 위', 'R1을 누른 채 왼쪽 스틱을 위로 밀어 보세요.', '앞으로 이동', 'ly', 1),
    ('ls', '↓', 'R1 + 왼쪽 스틱 아래', 'R1을 누른 채 왼쪽 스틱을 아래로 밀어 보세요.', '뒤로 이동', 'ly', -1),
    ('ls', '←', 'R1 + 왼쪽 스틱 왼쪽', 'R1을 누른 채 왼쪽 스틱을 왼쪽으로 밀어 보세요.', '왼쪽 이동', 'lx', -1),
    ('ls', '→', 'R1 + 왼쪽 스틱 오른쪽', 'R1을 누른 채 왼쪽 스틱을 오른쪽으로 밀어 보세요.', '오른쪽 이동', 'lx', 1),
    ('rs', '↑', 'R1 + 오른쪽 스틱 위', 'R1을 누른 채 오른쪽 스틱을 위로 밀어 보세요.', '높이 올리기', 'ry', 1),
    ('rs', '↓', 'R1 + 오른쪽 스틱 아래', 'R1을 누른 채 오른쪽 스틱을 아래로 밀어 보세요.', '높이 내리기', 'ry', -1),
    ('rs', '←', 'R1 + 오른쪽 스틱 왼쪽', 'R1을 누른 채 오른쪽 스틱을 왼쪽으로 밀어 보세요.', '손목 회전', 'rx', -1),
    ('rs', '→', 'R1 + 오른쪽 스틱 오른쪽', 'R1을 누른 채 오른쪽 스틱을 오른쪽으로 밀어 보세요.', '반대 방향 손목 회전', 'rx', 1),
    ('lt', 'L2', 'R1 + L2', 'R1을 누른 채 L2를 눌러 보세요.', '그리퍼 열기', 'lt', 1),
    ('rt', 'R2', 'R1 + R2', 'R1을 누른 채 R2를 눌러 보세요.', '그리퍼 닫기', 'rt', 1),
    ('back', 'SELECT', 'SELECT 버튼을 눌러 보세요', '실제 도전 중 SELECT를 누르면 도전과 이동 명령이 정지돼요.', '정지 요청', 'SELECT', 1),
)

class Practice:
    def __init__(self, cfg=None):
        cfg=cfg or {}; self.dz=cfg.get('deadzone',.15); self.steps=list(PRACTICE_STEPS)
        if cfg.get('swap_gripper',False):
            self.steps[9]=('rt','R2','R1 + R2','R1을 누른 채 R2를 눌러 보세요.','그리퍼 열기','rt',1)
            self.steps[10]=('lt','L2','R1 + L2','R1을 누른 채 L2를 눌러 보세요.','그리퍼 닫기','lt',1)
        for i,axis in [(1,'x'),(2,'x'),(3,'y'),(4,'y'),(5,'z'),(6,'z')]:
            if cfg.get(axis+'_sign',1)<0:
                other={1:'뒤로 이동',2:'앞으로 이동',3:'오른쪽 이동',4:'왼쪽 이동',5:'높이 내리기',6:'높이 올리기'}[i]
                st=self.steps[i]; self.steps[i]=(*st[:4],other,*st[5:])
        self.index=0; self.armed=False; self.since=None; self.feedback='release'; self.pause_until=0.; self.fraction=0.
    def update(self, now, s):
        if self.index>=len(self.steps): return
        if s is None:
            self.armed=False; self.since=None; self.fraction=0.; self.feedback='disconnected'; return
        if now<self.pause_until: return
        if not self.armed:
            self.feedback='release'; self.fraction=0.
            if neutral(s,self.dz) and s['btn']==0:
                self.armed=True; self.feedback='try'
            return
        key,_,_,_,_,axis,direction=self.steps[self.index]
        rb=bool(s['btn']&BUTTON['rb']); back=bool(s['btn']&BUTTON['back'])
        quiet=all(abs(s[k])<self.dz for k in AXES)
        if axis=='R1': ok=rb and not back and quiet
        elif axis=='SELECT': ok=back and not rb and quiet
        else:
            threshold=.5 if axis in ('lt','rt') else max(.55,self.dz+.05)
            ok=rb and not back and direction*s[axis]>=threshold and all(abs(s[k])<.35 for k in AXES if k!=axis)
        if ok:
            if self.since is None: self.since=now
            self.fraction=min(1.,(now-self.since)/.25); self.feedback='hold'
            if now-self.since>=.25: self.advance(now)
        else:
            self.since=None; self.fraction=0.; self.feedback='try'
    def advance(self,now):
        self.index+=1; self.armed=False; self.since=None; self.fraction=0.; self.pause_until=now+.65; self.feedback='correct'
    def status(self):
        n=len(self.steps); done=self.index>=n
        st=self.steps[min(self.index,n-1)]
        return dict(step=self.index,total=n,done=done,target=st[0],symbol=st[1],title=st[2],instruction=st[3],effect=st[4],feedback=self.feedback,fraction=self.fraction)

class Game:
    def __init__(self, records, cfg=None):
        self.cfg=cfg or {}; self.practice=None; self.records=records; self.refresh_records(); self.reset()
    def start_practice(self):
        if self.phase!='READY': return False
        self.practice=Practice(self.cfg); self.phase='PRACTICE'; self.enabled=False; self.message='연습 중에는 로봇팔 이동 명령과 기록 등록이 없습니다.'; return True
    def finish_practice(self):
        if self.phase!='PRACTICE': return False
        self.reset(); return True
    def refresh_records(self):
        self.boards=self.records.boards()
        self.ranking,self.wins,self.attempts=self.records.public(self.records.active_day)
    def begin(self,now,nickname,contact=''):
        if self.phase!='READY': return False
        self.rid=self.records.enter(nickname,contact); self.nickname=nickname
        self.refresh_records()
        self.phase='COUNTDOWN'; self.count_start=now; self.count='3'; self.elapsed=0.; self.enabled=False; self.message='잠시만 기다려 주세요.'; return True
    def tick(self,now):
        if self.phase=='COUNTDOWN':
            dt=now-self.count_start
            if dt<3: self.count=str(3-int(max(0,dt)))
            elif dt<COUNTDOWN: self.count='START!'
            else:
                self.phase='PLAY'; self.start=self.count_start+COUNTDOWN; self.elapsed=0.; self.enabled=False; self.message='R1을 누른 채 꽃을 잡아 보세요!'
        if self.phase=='PLAY':
            self.elapsed=min(DURATION,max(0,now-self.start))
            if self.elapsed>=DURATION: self.end('TIME UP','아쉽지만 시간이 끝났어요!')
    def end(self,phase,message):
        if self.phase not in ACTIVE or (phase=='SUCCESS' and self.phase!='PLAY'): return False
        self.phase=phase; self.message=message; self.enabled=False
        self.records.finish(self.rid,phase,self.elapsed)
        self.refresh_records(); return True
    def reset(self):
        if getattr(self,'phase',None) in ACTIVE: return
        self.practice=None; self.phase='READY'; self.nickname=''; self.rid=None; self.elapsed=0.; self.count='3'; self.enabled=False; self.message='닉네임을 입력하고 도전해 보세요!'

def participant(data):
    if not isinstance(data,dict): raise ValueError('입력 형식을 확인해 주세요.')
    n=data.get('nickname',''); c=data.get('contact','')
    if not isinstance(n,str) or not isinstance(c,str): raise ValueError('입력 형식을 확인해 주세요.')
    n=n.strip(); c=c.strip()
    if not 1<=len(n)<=16 or any(ord(x)<32 for x in n): raise ValueError('닉네임은 1~16자로 입력해 주세요.')
    if len(c)>40 or any(ord(x)<32 for x in c): raise ValueError('연락처는 40자 이내로 입력해 주세요.')
    if c and data.get('consent') is not True: raise ValueError('연락처 저장에 동의하거나 연락처를 비워 주세요.')
    return n,c

def neutral(s,dz=.15): return s is not None and all(abs(s[k])<dz for k in AXES) and not s['btn']&BUTTON['rb']
def action(s,cfg):
    dz=cfg.get('deadzone',.15)
    def a(k): return 0. if abs(s[k])<dz else max(-1.,min(1.,s[k]))
    close=s['rt']>.5; op=s['lt']>.5
    if cfg.get('swap_gripper',False): close,op=op,close
    xyz=[a('ly')*cfg.get('x_sign',1),-a('lx')*cfg.get('y_sign',1),a('ry')*cfg.get('z_sign',1)]
    norm=math.sqrt(sum(x*x for x in xyz)); xyz=[x/max(1,norm) for x in xyz]
    return xyz+[a('rx'),0 if close and not op else 2 if op and not close else 1]

class Demo:
    def __init__(self): self.xyz=[0.,0.,0.]; self.grip=0.; self.roll=0.
    def begin(self): pass
    def move(self,a):
        self.xyz=[max(-1,min(1,x+v*.025)) for x,v in zip(self.xyz,a[:3])]; self.roll+=a[3]*.8
        self.grip=max(0,min(100,self.grip+(2 if a[4]==0 else -2 if a[4]==2 else 0)))
    def status(self): return {'xyz':self.xyz,'grip':self.grip,'roll':self.roll}
    def close(self): pass

class Robot:
    def __init__(self,raw,safety,port):
        # Refuse to enable torque until an operator has measured exhibition-specific limits.
        import numpy as np
        self.np=np; self.robot=None; self.ctl=None
        if safety.get('verified') is not True: raise ValueError('safety.json: verified must be true after on-site checks')
        self.limits=np.asarray([safety['joint_limits'][n] for n in MOTORS],dtype=float)
        self.bounds={k:np.asarray(safety['workspace'][k],dtype=float) for k in ('min','max')}
        base=raw['env']['processor']['inverse_kinematics']['end_effector_bounds']
        if self.limits.shape!=(6,2) or not np.isfinite(self.limits).all() or (self.limits[:,0]>=self.limits[:,1]).any(): raise ValueError('joint limits invalid')
        if self.limits[-1,0]<0 or self.limits[-1,1]>100: raise ValueError('gripper limits must lie in 0..100')
        if any(v.shape!=(3,) or not np.isfinite(v).all() for v in self.bounds.values()) or (self.bounds['min']>=self.bounds['max']).any(): raise ValueError('workspace invalid')
        if (self.bounds['min']<base['min']).any() or (self.bounds['max']>base['max']).any(): raise ValueError('workspace must be inside original measured box')
        sys.path.insert(0,str(PARENT))
        from wrist_ee import WristEEController
        from teleop_test import sync_goal_to_present
        from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
        r=raw['env']['robot']; ik=raw['env']['processor']['inverse_kinematics']
        self.ctl=WristEEController(str(PARENT/ik['urdf_path']),ik['target_frame_name'],MOTORS,xyz_step=.002,roll_step=.8,grip_step=1.0,max_joint_step=1.0,bounds=self.bounds)
        # Preserve team IK ranges and tighten them; never broaden them.
        self.ctl.lo[:5]=np.maximum(self.ctl.lo[:5],self.limits[:5,0]); self.ctl.hi[:5]=np.minimum(self.ctl.hi[:5],self.limits[:5,1])
        self.limits[:5,0]=self.ctl.lo[:5]; self.limits[:5,1]=self.ctl.hi[:5]
        if (self.limits[:,0]>=self.limits[:,1]).any(): raise ValueError('limits conflict with URDF')
        sync_goal_to_present(port or r['port'])
        self.robot=SO101Follower(SO101FollowerConfig(port=port or r['port'],id=r['id'],disable_torque_on_disconnect=False,max_relative_target=2.0,cameras={}))
        try:
            self.robot.connect(calibrate=False)
            if not self.robot.is_calibrated: raise RuntimeError('Existing calibration required; do not calibrate during game')
            if list(self.robot.bus.motors)!=MOTORS: raise RuntimeError('Unexpected motor order')
            self.begin()
        except Exception:
            self.close(); raise
    def within(self,q,p):
        np=self.np
        return np.isfinite(q).all() and np.isfinite(p).all() and (q>=self.limits[:,0]).all() and (q<=self.limits[:,1]).all() and (p>=self.bounds['min']).all() and (p<=self.bounds['max']).all()
    def begin(self):
        obs=self.robot.get_observation(); q=self.np.array([obs[n+'.pos'] for n in MOTORS]); self.ctl.reset_from(q)
        if not self.within(q,self.ctl.p_cmd): raise RuntimeError('Current pose is outside verified limits')
    def move(self,a):
        np=self.np; prev=self.ctl.q_cmd.copy(); pp=self.ctl.p_cmd.copy(); pitch=self.ctl.pitch_cmd
        q=self.ctl.step(a); q[-1]=np.clip(q[-1],*self.limits[-1]); self.ctl.q_cmd[-1]=q[-1]
        p,_=self.ctl.ik.pose(q)
        if not self.within(q,p) or np.max(np.abs(q-prev))>1.001:
            self.ctl.q_cmd=prev; self.ctl.p_cmd=pp; self.ctl.pitch_cmd=pitch; return
        # Check measured pose and lag before sending next incremental goal.
        obs=self.robot.get_observation(); actual=np.array([obs[n+'.pos'] for n in MOTORS]); ap,_=self.ctl.ik.pose(actual)
        if not self.within(actual,ap) or np.max(np.abs(q-actual))>2.: raise RuntimeError('Actual position outside limits or excessive tracking lag')
        self.robot.send_action({n+'.pos':float(v) for n,v in zip(MOTORS,q)})
    def status(self): return {'xyz':self.ctl.p_cmd.tolist(),'grip':float(self.ctl.q_cmd[-1]),'roll':float(self.ctl.q_cmd[4])}
    def close(self):
        if self.robot is not None and self.robot.is_connected: self.robot.disconnect()


def administer(game, data):
    if game.phase in (*ACTIVE,'PRACTICE'): raise ValueError('도전 중에는 관리 기능을 사용할 수 없습니다.')
    r=game.records; op=data.get('op'); day=data.get('day')
    if op=='day':
        r.set_day(day); result={'message':f'{day}일차 기록 모드로 변경했습니다.'}
    elif op=='list': return r.list_runs(day,data.get('offset',0))
    elif op=='export': return {'csv':r.csv_text(day)}
    elif op=='delete':
        result={'message':f'{r.delete(data.get("id"))}개 기록을 삭제했습니다.'}
    elif op=='clear':
        if data.get('confirm')!='DELETE': raise ValueError('삭제 확인이 필요합니다.')
        result={'message':f'{r.clear(day)}개 기록을 삭제했습니다.'}
    else: raise ValueError('알 수 없는 관리 요청입니다.')
    game.refresh_records();return result

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--real',action='store_true'); ap.add_argument('--confirm-supervisor',action='store_true'); ap.add_argument('--ui-test',action='store_true',help='no pad or robot; only UI test'); ap.add_argument('--robot-port'); ap.add_argument('--pad-port',type=int,default=5567); ap.add_argument('--web-port',type=int,default=8091); ap.add_argument('--db',type=Path); ap.add_argument('--export-private',type=Path); args=ap.parse_args()
    if args.real and (not args.confirm_supervisor or args.ui_test): ap.error('--real requires --confirm-supervisor and cannot use --ui-test')
    db_path=args.db or Path.home()/'.local/share/kkotsooni_game'/('ui_test.sqlite3' if args.ui_test else 'real.sqlite3' if args.real else 'demo.sqlite3')
    records=Records(db_path)
    if args.export_private:
        records.export(args.export_private); print('Private CSV saved:',args.export_private); return
    raw=json.loads((PARENT/'configs/flower_hil.json').read_text()) if (PARENT/'configs/flower_hil.json').exists() else {'env':{'teleop':{}}}
    cfg=raw['env']['teleop']; game=Game(records,cfg); commands=queue.Queue(maxsize=32); token=secrets.token_urlsafe(24); stop=threading.Event(); shared={}; lock=threading.Lock(); hb=[0.]
    admin_pin=f'{secrets.randbelow(100_000_000):08d}'; auth_lock=threading.Lock(); failures=[0,0.]
    pad=Pad(args.pad_port)
    robot=Robot(raw,json.loads((HERE/'safety.json').read_text()),args.robot_port) if args.real else Demo()
    html=(HERE/'index.html').read_text(encoding='utf-8').replace('__TOKEN__',token)
    class H(BaseHTTPRequestHandler):
        def log_message(self,*a): pass
        def send(self,body,typ='application/json; charset=utf-8',code=200):
            self.send_response(code); self.send_header('Content-Type',typ); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        def reply(self,d,code=200):self.send(json.dumps(d,ensure_ascii=False).encode(),code=code)
        def do_GET(self):
            if urlsplit(self.path).path=='/': self.send(html.encode(),'text/html; charset=utf-8')
            elif urlsplit(self.path).path=='/status':
                with lock: data=dict(shared)
                self.reply(data)
            else: self.reply({},404)
        def do_POST(self):
            if self.headers.get('X-Game-Token')!=token: self.reply({},403); return
            cmd=urlsplit(self.path).path.strip('/')
            if cmd=='heartbeat': hb[0]=time.monotonic()
            elif cmd=='stop': stop.set()
            elif cmd=='admin':
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=4096: raise ValueError('요청 형식 오류')
                    self.connection.settimeout(2)
                    data=json.loads(self.rfile.read(length))
                    if not isinstance(data,dict): raise ValueError('요청 형식 오류')
                except (ValueError,TypeError,OSError): self.reply({'error':'요청 형식 오류'},400);return
                with auth_lock:
                    now=time.monotonic()
                    if now<failures[1]: self.reply({'error':'잠시 후 다시 시도해 주세요.'},429);return
                    pin=data.pop('pin','')
                    if not isinstance(pin,str) or not re.fullmatch(r"[0-9]{8}",pin) or not secrets.compare_digest(pin,admin_pin):
                        failures[0]+=1
                        if failures[0]>=5: failures[:]=[0,now+30]
                        self.reply({'error':'관리자 PIN이 틀렸습니다.'},403);return
                    failures[:]=[0,0.]
                future=Future()
                try:
                    commands.put_nowait(('admin',(data,future)))
                    result=future.result(timeout=5)
                except (queue.Full,FutureTimeout, CancelledError):
                    future.cancel();self.reply({'error':'관리 요청 처리 상태를 확인해 주세요.'},503);return
                except ValueError as e: self.reply({'error':str(e)},400);return
                self.reply(result);return
            elif cmd in ('start','success','reset','practice','practice-exit','practice-sample'):
                payload=None
                if cmd=='start':
                    try:
                        length=int(self.headers.get('Content-Length','0'))
                        if not 0<length<=2048: raise ValueError('입력 형식을 확인해 주세요.')
                        self.connection.settimeout(1)
                        payload=participant(json.loads(self.rfile.read(length)))
                    except (ValueError,TypeError,OSError) as e: self.reply({'error':str(e)},400); return
                try: commands.put_nowait((cmd,payload))
                except queue.Full: self.reply({'error':'다시 시도해 주세요.'},503); return
            else: self.reply({},404); return
            self.reply({'ok':True})
    try:
        server=ThreadingHTTPServer(('127.0.0.1',args.web_port),H); threading.Thread(target=server.serve_forever,daemon=True).start()
        mode='REAL' if args.real else 'UI TEST' if args.ui_test else 'DEMO'
        print(f'Windows browser: http://localhost:{args.web_port} | pad TCP {args.pad_port} | {mode}',flush=True)
        print('Local records:',db_path,flush=True)
        print('ADMIN PIN (this session only):',admin_pin,flush=True)
        while True:
            now=time.monotonic(); s=pad.get(); game.tick(now); browser_live=now-hb[0]<.7
            pad_ok=s is not None or args.ui_test
            if stop.is_set() or (game.phase in ACTIVE and (not pad_ok or not browser_live or bool(s and s['btn']&BUTTON['back']))):
                game.end('STOP','정지: 연결/SELECT/진행자 확인 필요'); game.finish_practice(); stop.clear()
                while not commands.empty():
                    dropped,payload=commands.get_nowait()
                    if dropped=='admin': payload[1].cancel()
            while not commands.empty():
                cmd,payload=commands.get_nowait()
                if cmd=='admin':
                    data,future=payload
                    if future.set_running_or_notify_cancel():
                        try: future.set_result(administer(game,data))
                        except (ValueError,sqlite3.Error) as e: future.set_exception(ValueError(str(e)))
                elif cmd=='reset': game.reset()
                elif cmd=='practice' and browser_live: game.start_practice()
                elif cmd=='practice-exit': game.finish_practice()
                elif cmd=='practice-sample' and args.ui_test and game.phase=='PRACTICE' and browser_live and game.practice.index<len(game.practice.steps) and now>=game.practice.pause_until: game.practice.advance(now)
                elif cmd=='start' and game.phase=='READY':
                    if browser_live and (args.ui_test or neutral(s,cfg.get('deadzone',.15))) and not (s and s['btn']&BUTTON['back']):
                        robot.begin(); game.begin(time.monotonic(),*payload)
                    else: game.message='게임패드를 연결하고 스틱과 버튼을 모두 놓은 뒤 다시 시작해 주세요.'
                elif cmd=='success': game.tick(time.monotonic()); game.end('SUCCESS','꽃 잡기 성공!')
            if game.phase=='PRACTICE':
                if not browser_live: game.finish_practice()
                elif not args.ui_test: game.practice.update(now,s)
                elif now>=game.practice.pause_until: game.practice.feedback='try'
            if game.phase=='PLAY' and s is not None and browser_live:
                if not s['btn']&BUTTON['rb']: game.enabled=neutral(s,cfg.get('deadzone',.15))
                if game.enabled and s['btn']&BUTTON['rb'] and not stop.is_set():
                    a=action(s,cfg)
                    if any(a[:4]) or a[4]!=1: robot.move(a)
            with lock: shared.update(phase=game.phase,count=game.count,elapsed=game.elapsed,remaining=max(0,DURATION-game.elapsed),nickname=game.nickname,wins=game.wins,attempts=game.attempts,ranking=game.ranking,boards=game.boards,active_day=records.active_day,message=game.message,pad=s is not None,pad_input={k:s[k] for k in (*AXES,'btn')} if s else None,can_start=bool(args.ui_test or (neutral(s,cfg.get('deadzone',.15)) and not s['btn']&BUTTON['back'])),enabled=bool(game.enabled and s and s['btn']&BUTTON['rb']),mode=mode,practice=game.practice.status() if game.phase=='PRACTICE' else None,swap_gripper=bool(cfg.get('swap_gripper',False)),axis_signs={k:cfg.get(k+'_sign',1) for k in ('x','y','z')},**robot.status())
            time.sleep(max(0,.05-(time.monotonic()-now)))
    except KeyboardInterrupt: pass
    finally:
        game.end('STOP','프로그램 종료'); robot.close(); pad.server.close()
        if 'server' in locals(): server.shutdown(); server.server_close()
        records.db.close()

if __name__=='__main__': main()
