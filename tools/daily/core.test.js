const fs=require('fs');const h=fs.readFileSync(require('path').join(__dirname,'index.html'),'utf8');
const X=new Function(h.split('/*core*/')[1].split('/*end*/')[0]+';return{cycleOf,compute,rollover,keyOf,parse,preview,ensure};')();
let f=0;const eq=(n,a,b)=>{const ok=typeof b==='number'?Math.abs(a-b)<0.01:a===b;if(!ok)f++;console.log(ok?'ok  ':'FAIL',n,a,b)};
const P=X.parse,K=X.keyOf;
let c=X.cycleOf(P('2026-10-14'),10);eq('start',K(c.start),'2026-10-10');eq('end',K(c.end),'2026-11-10');
c=X.cycleOf(P('2026-10-05'),10);eq('before payday',K(c.start),'2026-09-10');
c=X.cycleOf(P('2027-01-03'),15);eq('cross year',K(c.start),'2026-12-15');eq('cross year end',K(c.end),'2027-01-15');
c=X.cycleOf(P('2027-02-28'),31);eq('feb31',K(c.start),'2027-02-28');eq('feb31 end',K(c.end),'2027-03-31');
c=X.cycleOf(P('2026-11-29'),31);eq('nov',K(c.start),'2026-10-31');eq('nov end',K(c.end),'2026-11-30');
const setup={payday:10,income:8000,fixed:[{n:'房租',a:2500},{n:'话费',a:100}],save:800};
// avail 4600, cycle 10/10-11/10 = 31 days; today 10/14 -> daysLeft 27
let D={setup,entries:[],cycle:{start:'2026-10-10'},since:'2026-10-10'};
let R=X.compute(D,P('2026-10-14'));eq('avail',R.avail,4600);eq('daysLeft',R.daysLeft,27);eq('allow',R.allowance,4600/27);
D.entries=[{d:'2026-10-10',a:300},{d:'2026-10-12',a:200},{d:'2026-10-14',a:100}];
R=X.compute(D,P('2026-10-14'));eq('allow2',R.allowance,4100/27);eq('todayLeft',R.todayLeft,4100/27-100);eq('remain',R.remain,4000);eq('tomorrow',R.tomorrow,4000/26);
D.entries.push({d:'2026-10-14',a:-260});R=X.compute(D,P('2026-10-14'));eq('income spread',R.allowance,(4100+260)/27);eq('spentToday ignores income',R.spentToday,100);
// overspend whole cycle
D.entries=[{d:'2026-10-11',a:5000}];R=X.compute(D,P('2026-10-14'));eq('over allow',R.allowance,0);eq('over remain',R.remain,-400);
// pace: 3 days of 400/day from since 10/12 -> avg 400
D={setup,entries:[{d:'2026-10-12',a:400},{d:'2026-10-13',a:400},{d:'2026-10-14',a:400}],cycle:{start:'2026-10-10'},since:'2026-10-12'};
R=X.compute(D,P('2026-10-14'));console.log(R.pace);eq('pace short',R.pace.short,true);
// '之前' entry excluded from pace avg
D={setup,entries:[{d:'2026-10-10',a:2000,c:'之前'},{d:'2026-10-12',a:50},{d:'2026-10-13',a:50},{d:'2026-10-14',a:50}],cycle:{start:'2026-10-10'},since:'2026-10-12'};
R=X.compute(D,P('2026-10-14'));eq('pace avg',R.pace.avg,50);eq('pace ok',R.pace.short,false);
// last day
R=X.compute(D,P('2026-11-09'));eq('last day left',R.daysLeft,1);eq('tomorrow null',R.tomorrow,null);
// rollover
D={setup,entries:[{d:'2026-10-12',a:1000},{d:'2026-11-10',a:50}],cycle:{start:'2026-10-10',avail:4600,saved:true,planSave:800},history:[]};
const e=X.rollover(D,P('2026-11-11'));eq('roll left',e.left,3600);eq('new start',D.cycle.start,'2026-11-10');eq('saved flag reset',D.cycle.saved,false);
eq('no double roll',X.rollover(D,P('2026-11-12')),null);
// preview does not mutate, and matches a real entry
D={setup,entries:[{d:'2026-10-14',a:100}],cycle:{start:'2026-10-10'},since:'2026-10-10'};
const before=JSON.stringify(D);
const pv=X.preview(D,P('2026-10-14'),35,false);
eq('preview no mutate',JSON.stringify(D),before);
D.entries.push({d:'2026-10-14',a:35});
R=X.compute(D,P('2026-10-14'));
eq('preview today',pv.todayLeft,R.todayLeft);
eq('preview tomorrow',pv.tomorrow,R.tomorrow);
// src save is ignored by the daily allowance; caller owns savedTotal
D={setup,entries:[{d:'2026-10-14',a:500,src:'save'}],cycle:{start:'2026-10-10'},since:'2026-10-10',savedTotal:800};
R=X.compute(D,P('2026-10-14'));
eq('save src allow',R.allowance,4600/27);
eq('save src spent',R.spentToday,0);
eq('save src remain',R.remain,4600);
eq('savedTotal untouched',D.savedTotal,800);
// v1 payload without days/ui still computes, and ensure fills the new fields
let old={setup,entries:[{d:'2026-10-14',a:100}],savedTotal:0,history:[],cycle:{start:'2026-10-10'},ended:null,since:'2026-10-10'};
R=X.compute(old,P('2026-10-14'));
eq('v1 todayLeft',R.todayLeft,4600/27-100);
X.ensure(old);
eq('v1 days',typeof old.days,'object');
eq('v1 ui',typeof old.ui,'object');
eq('v1 still',X.compute(old,P('2026-10-14')).allowance,4600/27);
console.log(f?'FAILED '+f:'ALL PASS');
