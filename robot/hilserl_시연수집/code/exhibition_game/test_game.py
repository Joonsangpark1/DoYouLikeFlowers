import tempfile, unittest
from pathlib import Path
from flower_game import Game, Records, participant, action, neutral, Demo, administer, Practice, AXES, BUTTON
import sqlite3
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'records.db';self.r=Records(self.path);self.g=Game(self.r)
    def tearDown(self):self.r.db.close();self.tmp.cleanup()
    def test_count(self):
        g=self.g;g.begin(100,'테스트');g.tick(100);self.assertEqual(g.count,'3');g.tick(101);self.assertEqual(g.count,'2');g.tick(102);self.assertEqual(g.count,'1');g.tick(103);self.assertEqual(g.count,'START!');g.tick(103.65);self.assertEqual(g.phase,'PLAY');g.tick(105);self.assertAlmostEqual(g.elapsed,1.35)
    def test_timeout(self):
        g=self.g;g.begin(100,'테스트');g.tick(163.65);self.assertEqual(g.phase,'TIME UP');self.assertFalse(g.end('SUCCESS',''));self.assertEqual(g.ranking,[])
    def test_persistence_and_order(self):
        g=self.g
        for name,t in [('A',12),('B',8),('C',9),('A',7),('D',20)]:
            g.begin(100,name,'private-'+name);g.tick(103.65+t);g.end('SUCCESS','');g.reset()
        r=Records(self.path);rank,w,a=r.public();r.db.close();self.assertEqual([x['nickname'] for x in rank],['A','B','C']);self.assertEqual((w,a),(5,5));self.assertNotIn('private',str(rank))
    def test_stop_countdown(self):
        g=self.g;g.begin(0,'A');self.assertFalse(g.end('SUCCESS',''));g.end('STOP','');g.tick(5);self.assertEqual(g.phase,'STOP');g.reset();self.assertEqual(g.phase,'READY')
    def test_participant(self):
        self.assertEqual(participant({'nickname':' A ','contact':'','consent':False}),('A',''));self.assertRaises(ValueError,participant,{'nickname':'A','contact':'123'});self.assertEqual(participant({'nickname':'A','contact':'123','consent':True}),('A','123'))
    def test_input(self):
        s=dict(lx=0,ly=1,rx=0,ry=0,lt=0,rt=1,btn=512);self.assertEqual(action(s,{}),[1,0,0,0,0]);s['lt']=1;self.assertEqual(action(s,{})[-1],1);self.assertFalse(neutral(s))
    def record(self,name,contact,t):
        self.g.begin(100,name,contact);self.g.tick(103.65+t);self.g.end('SUCCESS','');self.g.reset()
    def test_days_and_identity(self):
        self.record('같은닉','010-1111-2222',12)
        self.record('같은닉','010-3333-4444',10)
        self.record('같은닉','01011112222',8)
        self.assertEqual([x['ms'] for x in self.r.public(1)[0]],[8000,10000])
        administer(self.g,{'op':'day','day':2})
        self.record('다른닉','01011112222',5)
        self.record('손님','',7);self.record('손님','',6)
        self.assertEqual([x['ms'] for x in self.r.public(1)[0]],[8000,10000])
        self.assertEqual([x['ms'] for x in self.r.public(2)[0]],[5000,6000,7000])
        self.assertEqual([x['ms'] for x in self.r.public('all')[0]],[5000,6000,7000])
        self.assertNotIn('010',str(self.r.boards()))
        other=Records(self.path);self.assertEqual(other.active_day,2);other.db.close()
    def test_admin_delete_clear_export(self):
        self.record('A','010-1234',10);self.record('B','',8)
        administer(self.g,{'op':'day','day':2});self.record('C','',6)
        rows=administer(self.g,{'op':'list','day':1})['rows'];self.assertEqual(len(rows),2)
        self.assertNotIn('010',str(rows))
        self.assertIn('010-1234',administer(self.g,{'op':'export','day':1})['csv'])
        administer(self.g,{'op':'delete','id':rows[0]['id']})
        self.assertEqual(self.r.public(1)[2],1)
        with self.assertRaises(ValueError):administer(self.g,{'op':'clear','day':1})
        administer(self.g,{'op':'clear','day':1,'confirm':'DELETE'})
        self.assertEqual(self.r.public(1)[2],0);self.assertEqual(self.r.public(2)[2],1)
    def test_active_lock(self):
        self.g.begin(100,'A')
        with self.assertRaises(ValueError):administer(self.g,{'op':'day','day':2})
        with self.assertRaises(ValueError):administer(self.g,{'op':'clear','day':'all','confirm':'DELETE'})
    def test_v2_migration(self):
        old=Path(self.tmp.name)/'old.db';c=sqlite3.connect(old)
        c.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY,nickname TEXT NOT NULL,contact TEXT NOT NULL,result TEXT NOT NULL DEFAULT 'IN_PROGRESS',ms INTEGER,created TEXT DEFAULT CURRENT_TIMESTAMP)")
        c.execute("INSERT INTO runs(nickname,contact,result,ms) VALUES ('old','','SUCCESS',1234)");c.commit();c.close()
        r=Records(old);self.assertEqual(r.public(1)[0][0]['ms'],1234);self.assertEqual(r.public(2)[2],0);self.assertEqual(len(list(old.parent.glob('old.db.v2-backup-*'))),1);r.db.close()
    def test_practice_isolated(self):
        g=self.g;self.assertTrue(g.start_practice());self.assertEqual(g.phase,'PRACTICE');self.assertFalse(g.begin(0,'A'));self.assertFalse(g.end('SUCCESS',''));g.tick(1000);self.assertEqual(g.elapsed,0);self.assertEqual(self.r.public()[2],0)
        with self.assertRaises(ValueError):administer(g,{'op':'day','day':2})
        self.assertTrue(g.finish_practice());self.assertEqual(g.phase,'READY');self.assertIsNone(g.practice)
    def test_practice_full_sequence(self):
        p=Practice();s={**dict.fromkeys(AXES,0),'btn':0};now=0.
        for i,step in enumerate(p.steps):
            axis,direction=step[-2:];target=dict(s)
            if axis=='R1':target['btn']=BUTTON['rb']
            elif axis=='SELECT':target['btn']=BUTTON['back']
            else:target.update(btn=BUTTON['rb']);target[axis]=direction
            # Already-held keys cannot auto-pass; release, then deliberately input.
            p.update(now,target);p.update(now+.4,target);self.assertEqual(p.index,i)
            p.update(now+.5,s);p.update(now+.6,target);p.update(now+.9,target);self.assertEqual(p.index,i+1)
            now+=2
        self.assertTrue(p.status()['done'])
    def test_practice_requires_r1_and_fresh_input(self):
        p=Practice();s={**dict.fromkeys(AXES,0),'btn':0};p.update(0,s);p.update(.1,{**s,'btn':512});p.update(.4,{**s,'btn':512});self.assertEqual(p.index,1)
        p.update(2,s);p.update(2.1,{**s,'ly':1});p.update(2.5,{**s,'ly':1});self.assertEqual(p.index,1)
        p.update(2.6,{**s,'ly':-1,'btn':512});p.update(3,{**s,'ly':-1,'btn':512});self.assertEqual(p.index,1)
        p.update(3.1,{**s,'ly':1,'btn':512});p.update(3.2,None);p.update(4,{**s,'ly':1,'btn':512});self.assertEqual(p.index,1)
        p.update(4.1,s);p.update(4.2,{**s,'ly':1,'btn':512});p.update(4.6,{**s,'ly':1,'btn':512});self.assertEqual(p.index,2)
if __name__=='__main__':unittest.main()
