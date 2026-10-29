// ==UserScript==
// @name         Шахматный помощник — стрелки (только против ботов)
// @namespace    reeni-dotagame
// @version      1.0
// @description  Показывает стрелкой лучший ход в партиях против ботов на chess.com и lichess.org
// @match        https://www.chess.com/*
// @match        https://lichess.org/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function(){
'use strict';

// Движок — тот же, что в chess.html. Обёрнут в функцию, чтобы запускать его
// и на странице, и в Web Worker (через Blob).
const engineFactory=function(){
const P=1, N=2, B=3, R=4, Q=5, K=6, BL=8;
const F_EP=1, F_CASTLE=2, F_DOUBLE=4;
const VAL=[0,100,320,330,500,900,0];
const PHASE=[0,0,1,1,2,4,0];
const MATE=30000, INF=32000, MAXPLY=64;
const START_FEN="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

function mv(f,t,pr,fl){ return f|(t<<6)|(pr<<12)|(fl<<15); }
const mFrom=m=>m&63, mTo=m=>(m>>6)&63, mPromo=m=>(m>>12)&7, mFlags=m=>(m>>15)&7;

function sqName(s){ return "abcdefgh"[s&7]+(8-(s>>3)); }
function sqIndex(n){ return (8-(+n[1]))*8+(n.charCodeAt(0)-97); }

// заранее посчитанные ходы коня, короля и лучи
const KN=[], KG=[], RAYS=[];
const DIRS=[[-1,0],[1,0],[0,-1],[0,1],[-1,-1],[-1,1],[1,-1],[1,1]];
for(let s=0;s<64;s++){
  const r=s>>3, f=s&7;
  KN[s]=[]; KG[s]=[]; RAYS[s]=[];
  for(const [dr,df] of [[-2,-1],[-2,1],[-1,-2],[-1,2],[1,-2],[1,2],[2,-1],[2,1]]){
    const rr=r+dr, ff=f+df;
    if(rr>=0&&rr<8&&ff>=0&&ff<8) KN[s].push(rr*8+ff);
  }
  for(const [dr,df] of DIRS){
    const rr=r+dr, ff=f+df;
    if(rr>=0&&rr<8&&ff>=0&&ff<8) KG[s].push(rr*8+ff);
    const ray=[];
    let a=r+dr, c=f+df;
    while(a>=0&&a<8&&c>=0&&c<8){ ray.push(a*8+c); a+=dr; c+=df; }
    RAYS[s].push(ray);
  }
}

// маска прав рокировки: какие права теряются, если с поля/на поле ходят
const CASTLE_MASK=new Array(64).fill(15);
CASTLE_MASK[60]=15&~3; CASTLE_MASK[63]=15&~1; CASTLE_MASK[56]=15&~2;
CASTLE_MASK[4]=15&~12; CASTLE_MASK[7]=15&~4;  CASTLE_MASK[0]=15&~8;

// хеши Зобриста
let seed=0x9E3779B9;
function rnd(){ seed^=seed<<13; seed^=seed>>>17; seed^=seed<<5; return seed|0; }
const ZP=[]; for(let p=0;p<16;p++){ ZP[p]=[]; for(let s=0;s<64;s++) ZP[p][s]=rnd(); }
const ZSIDE=rnd();
const ZC=[]; for(let i=0;i<16;i++) ZC[i]=rnd();
const ZEP=[]; for(let i=0;i<8;i++) ZEP[i]=rnd();

// таблицы позиционной оценки (для белых, a8 = 0)
const PST=[[],
[ 0,0,0,0,0,0,0,0, 50,50,50,50,50,50,50,50, 10,10,20,30,30,20,10,10, 5,5,10,25,25,10,5,5,
  0,0,0,20,20,0,0,0, 5,-5,-10,0,0,-10,-5,5, 5,10,10,-20,-20,10,10,5, 0,0,0,0,0,0,0,0],
[ -50,-40,-30,-30,-30,-30,-40,-50, -40,-20,0,0,0,0,-20,-40, -30,0,10,15,15,10,0,-30, -30,5,15,20,20,15,5,-30,
  -30,0,15,20,20,15,0,-30, -30,5,10,15,15,10,5,-30, -40,-20,0,5,5,0,-20,-40, -50,-40,-30,-30,-30,-30,-40,-50],
[ -20,-10,-10,-10,-10,-10,-10,-20, -10,0,0,0,0,0,0,-10, -10,0,5,10,10,5,0,-10, -10,5,5,10,10,5,5,-10,
  -10,0,10,10,10,10,0,-10, -10,10,10,10,10,10,10,-10, -10,5,0,0,0,0,5,-10, -20,-10,-10,-10,-10,-10,-10,-20],
[ 0,0,0,0,0,0,0,0, 5,10,10,10,10,10,10,5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5,
  -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, 0,0,0,5,5,0,0,0],
[ -20,-10,-10,-5,-5,-10,-10,-20, -10,0,0,0,0,0,0,-10, -10,0,5,5,5,5,0,-10, -5,0,5,5,5,5,0,-5,
  0,0,5,5,5,5,0,-5, -10,5,5,5,5,5,0,-10, -10,0,5,0,0,0,0,-10, -20,-10,-10,-5,-5,-10,-10,-20],
[ -30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30,
  -20,-30,-30,-40,-40,-30,-30,-20, -10,-20,-20,-20,-20,-20,-20,-10, 20,20,0,0,0,0,20,20, 20,30,10,0,0,10,30,20]
];
const KING_END=[ -50,-40,-30,-20,-20,-30,-40,-50, -30,-20,-10,0,0,-10,-20,-30, -30,-10,20,30,30,20,-10,-30, -30,-10,30,40,40,30,-10,-30,
  -30,-10,30,40,40,30,-10,-30, -30,-10,20,30,30,20,-10,-30, -30,-30,0,0,0,0,-30,-30, -50,-30,-30,-30,-30,-30,-30,-50];
const PASSED_MG=[0,5,10,15,25,40,0], PASSED_EG=[0,10,20,35,60,100,0];

const TT_SIZE=1<<19, TT_MASK=TT_SIZE-1;
const TT_EXACT=1, TT_LOWER=2, TT_UPPER=3;

function Pos(){
  this.b=new Int8Array(64);
  this.side=0; this.castle=0; this.ep=-1; this.half=0; this.full=1;
  this.kings=[60,4]; this.hash=0; this.hist=[];
}

Pos.prototype.load=function(fen){
  const parts=fen.trim().split(/\s+/);
  const rows=(parts[0]||"").split("/");
  if(rows.length!==8) throw new Error("FEN: нужно 8 рядов");
  this.b.fill(0);
  let wk=0, bk=0;
  for(let r=0;r<8;r++){
    let f=0;
    for(const ch of rows[r]){
      if(ch>="1"&&ch<="8"){ f+=+ch; continue; }
      const t="pnbrqk".indexOf(ch.toLowerCase())+1;
      if(!t||f>7) throw new Error("FEN: неверный символ "+ch);
      const p=t|(ch===ch.toLowerCase()?BL:0);
      this.b[r*8+f]=p;
      if(p===K){ this.kings[0]=r*8+f; wk++; }
      if(p===(K|BL)){ this.kings[1]=r*8+f; bk++; }
      f++;
    }
    if(f!==8) throw new Error("FEN: в ряду должно быть 8 полей");
  }
  if(wk!==1||bk!==1) throw new Error("FEN: нужен ровно один король каждого цвета");
  this.side=parts[1]==="b"?BL:0;
  const c=parts[2]||"-";
  this.castle=(c.includes("K")?1:0)|(c.includes("Q")?2:0)|(c.includes("k")?4:0)|(c.includes("q")?8:0);
  this.ep=(parts[3]&&parts[3]!=="-")?sqIndex(parts[3]):-1;
  this.half=+(parts[4]||0)||0;
  this.full=+(parts[5]||1)||1;
  this.hist=[];
  this.hash=this.computeHash();
  return this;
};

Pos.prototype.fen=function(){
  let s="";
  for(let r=0;r<8;r++){
    let e=0;
    for(let f=0;f<8;f++){
      const p=this.b[r*8+f];
      if(!p){ e++; continue; }
      if(e){ s+=e; e=0; }
      const ch=" pnbrqk"[p&7];
      s+=(p&BL)?ch:ch.toUpperCase();
    }
    if(e) s+=e;
    if(r<7) s+="/";
  }
  let c=(this.castle&1?"K":"")+(this.castle&2?"Q":"")+(this.castle&4?"k":"")+(this.castle&8?"q":"");
  return s+" "+(this.side?"b":"w")+" "+(c||"-")+" "+(this.ep>=0?sqName(this.ep):"-")+" "+this.half+" "+this.full;
};

Pos.prototype.computeHash=function(){
  let h=0;
  for(let s=0;s<64;s++) if(this.b[s]) h^=ZP[this.b[s]][s];
  if(this.side) h^=ZSIDE;
  h^=ZC[this.castle];
  if(this.ep>=0) h^=ZEP[this.ep&7];
  return h;
};

Pos.prototype.clone=function(){
  const p=new Pos();
  p.b.set(this.b);
  p.side=this.side; p.castle=this.castle; p.ep=this.ep; p.half=this.half; p.full=this.full;
  p.kings=this.kings.slice(); p.hash=this.hash; p.hist=this.hist.slice();
  return p;
};

Pos.prototype.attacked=function(sq,by){
  const b=this.b, r=sq>>3, f=sq&7;
  if(by===0){
    if(r<7){ if(f>0&&b[sq+7]===P) return true; if(f<7&&b[sq+9]===P) return true; }
  }else{
    if(r>0){ if(f>0&&b[sq-9]===(P|BL)) return true; if(f<7&&b[sq-7]===(P|BL)) return true; }
  }
  const n=N|by, k=K|by, q=Q|by, rk=R|by, bs=B|by;
  const kn=KN[sq]; for(let i=0;i<kn.length;i++) if(b[kn[i]]===n) return true;
  const kg=KG[sq]; for(let i=0;i<kg.length;i++) if(b[kg[i]]===k) return true;
  const rays=RAYS[sq];
  for(let d=0;d<8;d++){
    const ray=rays[d];
    for(let i=0;i<ray.length;i++){
      const p=b[ray[i]];
      if(p){ if(p===q||(d<4?p===rk:p===bs)) return true; break; }
    }
  }
  return false;
};

Pos.prototype.inCheck=function(){ return this.attacked(this.kings[this.side>>3],this.side^BL); };

// псевдолегальные ходы; caps=true — только взятия и превращения (для quiescence)
Pos.prototype.gen=function(caps){
  const b=this.b, us=this.side, them=us^BL, out=[];
  const promoTypes=caps?[Q]:[Q,R,B,N];
  for(let s=0;s<64;s++){
    const p=b[s];
    if(!p||(p&BL)!==us) continue;
    const t=p&7;
    if(t===P){
      const dir=us?8:-8, r=s>>3, f=s&7, to=s+dir, promo=(to>>3)===(us?7:0);
      if(b[to]===0&&(!caps||promo)){
        if(promo){ for(const pt of promoTypes) out.push(mv(s,to,pt,0)); }
        else{
          out.push(mv(s,to,0,0));
          if(r===(us?1:6)&&b[to+dir]===0) out.push(mv(s,to+dir,0,F_DOUBLE));
        }
      }
      for(let df=-1;df<=1;df+=2){
        if(f+df<0||f+df>7) continue;
        const c=to+df, q=b[c];
        if(q&&(q&BL)===them){
          if(promo){ for(const pt of promoTypes) out.push(mv(s,c,pt,0)); }
          else out.push(mv(s,c,0,0));
        }else if(c===this.ep) out.push(mv(s,c,0,F_EP));
      }
    }else if(t===N||t===K){
      const tg=t===N?KN[s]:KG[s];
      for(let i=0;i<tg.length;i++){
        const to=tg[i], q=b[to];
        if(!q){ if(!caps) out.push(mv(s,to,0,0)); }
        else if((q&BL)===them) out.push(mv(s,to,0,0));
      }
      if(t===K&&!caps){
        if(us===0&&s===60){
          if((this.castle&1)&&!b[61]&&!b[62]&&b[63]===R&&!this.attacked(60,BL)&&!this.attacked(61,BL)&&!this.attacked(62,BL)) out.push(mv(60,62,0,F_CASTLE));
          if((this.castle&2)&&!b[59]&&!b[58]&&!b[57]&&b[56]===R&&!this.attacked(60,BL)&&!this.attacked(59,BL)&&!this.attacked(58,BL)) out.push(mv(60,58,0,F_CASTLE));
        }else if(us===BL&&s===4){
          if((this.castle&4)&&!b[5]&&!b[6]&&b[7]===(R|BL)&&!this.attacked(4,0)&&!this.attacked(5,0)&&!this.attacked(6,0)) out.push(mv(4,6,0,F_CASTLE));
          if((this.castle&8)&&!b[3]&&!b[2]&&!b[1]&&b[0]===(R|BL)&&!this.attacked(4,0)&&!this.attacked(3,0)&&!this.attacked(2,0)) out.push(mv(4,2,0,F_CASTLE));
        }
      }
    }else{
      const d0=t===B?4:0, d1=t===R?4:8, rays=RAYS[s];
      for(let d=d0;d<d1;d++){
        const ray=rays[d];
        for(let i=0;i<ray.length;i++){
          const to=ray[i], q=b[to];
          if(!q){ if(!caps) out.push(mv(s,to,0,0)); continue; }
          if((q&BL)===them) out.push(mv(s,to,0,0));
          break;
        }
      }
    }
  }
  return out;
};

Pos.prototype.make=function(m){
  const b=this.b, from=mFrom(m), to=mTo(m), pr=mPromo(m), fl=mFlags(m), us=this.side;
  const p=b[from];
  let cap=b[to], capSq=to;
  this.hist.push({m, cap:0, capSq:0, castle:this.castle, ep:this.ep, half:this.half, hash:this.hash});
  const h=this.hist[this.hist.length-1];
  let hash=this.hash^ZP[p][from];
  if(fl&F_EP){ capSq=to+(us?-8:8); cap=b[capSq]; b[capSq]=0; }
  if(cap) hash^=ZP[cap][capSq];
  h.cap=cap; h.capSq=capSq;
  b[from]=0;
  const placed=pr?(pr|us):p;
  b[to]=placed; hash^=ZP[placed][to];
  if(fl&F_CASTLE){
    let rf, rt;
    if(to===62){rf=63;rt=61;} else if(to===58){rf=56;rt=59;} else if(to===6){rf=7;rt=5;} else {rf=0;rt=3;}
    const rk=b[rf]; b[rf]=0; b[rt]=rk; hash^=ZP[rk][rf]^ZP[rk][rt];
  }
  if((p&7)===K) this.kings[us>>3]=to;
  hash^=ZC[this.castle];
  this.castle&=CASTLE_MASK[from]&CASTLE_MASK[to];
  hash^=ZC[this.castle];
  if(this.ep>=0) hash^=ZEP[this.ep&7];
  this.ep=(fl&F_DOUBLE)?(from+to)>>1:-1;
  if(this.ep>=0) hash^=ZEP[this.ep&7];
  this.half=((p&7)===P||cap)?0:this.half+1;
  if(us) this.full++;
  this.side=us^BL;
  this.hash=hash^ZSIDE;
};

Pos.prototype.unmake=function(){
  const h=this.hist.pop(), m=h.m, b=this.b;
  const from=mFrom(m), to=mTo(m), fl=mFlags(m);
  this.side^=BL;
  const us=this.side;
  let p=b[to];
  if(mPromo(m)) p=P|us;
  b[from]=p; b[to]=0;
  b[h.capSq]=h.cap;
  if(fl&F_CASTLE){
    let rf, rt;
    if(to===62){rf=63;rt=61;} else if(to===58){rf=56;rt=59;} else if(to===6){rf=7;rt=5;} else {rf=0;rt=3;}
    b[rf]=b[rt]; b[rt]=0;
  }
  if((p&7)===K) this.kings[us>>3]=from;
  this.castle=h.castle; this.ep=h.ep; this.half=h.half; this.hash=h.hash;
  if(us) this.full--;
};

Pos.prototype.makeNull=function(){
  this.hist.push({m:0, cap:0, capSq:0, castle:this.castle, ep:this.ep, half:this.half, hash:this.hash});
  let hash=this.hash;
  if(this.ep>=0) hash^=ZEP[this.ep&7];
  this.ep=-1; this.half++;
  this.side^=BL;
  this.hash=hash^ZSIDE;
};

Pos.prototype.unmakeNull=function(){
  const h=this.hist.pop();
  this.side^=BL;
  this.ep=h.ep; this.half=h.half; this.hash=h.hash;
};

Pos.prototype.legal=function(){
  const out=[], us=this.side, ms=this.gen(false);
  for(const m of ms){
    this.make(m);
    if(!this.attacked(this.kings[us>>3],this.side)) out.push(m);
    this.unmake();
  }
  return out;
};

Pos.prototype.isRep=function(){
  const h=this.hist, stop=Math.max(0,h.length-this.half);
  for(let i=h.length-2;i>=stop;i-=2) if(h[i].hash===this.hash) return true;
  return false;
};

Pos.prototype.repCount=function(){
  let n=1;
  const h=this.hist, stop=Math.max(0,h.length-this.half);
  for(let i=h.length-2;i>=stop;i-=2) if(h[i].hash===this.hash) n++;
  return n;
};

Pos.prototype.insufficient=function(){
  let minors=0;
  for(let s=0;s<64;s++){
    const t=this.b[s]&7;
    if(t===P||t===R||t===Q) return false;
    if(t===N||t===B) minors++;
  }
  return minors<=1;
};

Pos.prototype.hasPieces=function(us){
  for(let s=0;s<64;s++){
    const p=this.b[s];
    if(p&&(p&BL)===us){ const t=p&7; if(t!==P&&t!==K) return true; }
  }
  return false;
};

// оценка позиции с точки зрения стороны, которая ходит
Pos.prototype.evaluate=function(){
  const b=this.b;
  const wMax=[-1,-1,-1,-1,-1,-1,-1,-1], bMin=[8,8,8,8,8,8,8,8];
  const wCnt=[0,0,0,0,0,0,0,0], bCnt=[0,0,0,0,0,0,0,0];
  for(let s=8;s<56;s++){
    const p=b[s];
    if(p===P){ const f=s&7, r=s>>3; wCnt[f]++; if(r>wMax[f]) wMax[f]=r; }
    else if(p===(P|BL)){ const f=s&7, r=s>>3; bCnt[f]++; if(r<bMin[f]) bMin[f]=r; }
  }
  let mg=0, eg=0, ph=0, wMat=0, bMat=0, wPawns=0, bPawns=0, wB=0, bB=0;
  for(let s=0;s<64;s++){
    const p=b[s];
    if(!p) continue;
    const t=p&7, white=!(p&BL), i=white?s:s^56;
    let vm=VAL[t]+PST[t][i], ve=VAL[t]+(t===K?KING_END[i]:PST[t][i]);
    ph+=PHASE[t];
    const f=s&7, r=s>>3;
    if(t===P){
      if(white){
        wPawns++;
        if((f===0||bMin[f-1]>=r)&&bMin[f]>=r&&(f===7||bMin[f+1]>=r)){ vm+=PASSED_MG[6-r]; ve+=PASSED_EG[6-r]; }
      }else{
        bPawns++;
        if((f===0||wMax[f-1]<=r)&&wMax[f]<=r&&(f===7||wMax[f+1]<=r)){ vm+=PASSED_MG[r-1]; ve+=PASSED_EG[r-1]; }
      }
    }else if(t!==K){
      if(white) wMat+=VAL[t]; else bMat+=VAL[t];
      if(t===B){ if(white) wB++; else bB++; }
      if(t===R){
        const own=white?wCnt[f]:bCnt[f], opp=white?bCnt[f]:wCnt[f];
        if(!own){ const bonus=opp?8:16; vm+=bonus; ve+=bonus; }
      }
    }
    if(white){ mg+=vm; eg+=ve; } else { mg-=vm; eg-=ve; }
  }
  for(let f=0;f<8;f++){
    if(wCnt[f]>1){ mg-=10*(wCnt[f]-1); eg-=20*(wCnt[f]-1); }
    if(bCnt[f]>1){ mg+=10*(bCnt[f]-1); eg+=20*(bCnt[f]-1); }
    if(wCnt[f]&&(f===0||!wCnt[f-1])&&(f===7||!wCnt[f+1])){ mg-=10*wCnt[f]; eg-=15*wCnt[f]; }
    if(bCnt[f]&&(f===0||!bCnt[f-1])&&(f===7||!bCnt[f+1])){ mg+=10*bCnt[f]; eg+=15*bCnt[f]; }
  }
  if(wB>=2){ mg+=30; eg+=50; }
  if(bB>=2){ mg-=30; eg-=50; }
  if(ph>24) ph=24;
  let sc=((mg*ph+eg*(24-ph))/24)|0;

  // в эндшпиле с большим перевесом — прижимать короля к краю (помогает ставить мат)
  if(ph<=8){
    const diff=(wMat+wPawns*100)-(bMat+bPawns*100);
    if(diff>=400||diff<=-400){
      const weak=diff>0?this.kings[1]:this.kings[0], strong=diff>0?this.kings[0]:this.kings[1];
      const wr=weak>>3, wf=weak&7, sr=strong>>3, sf=strong&7;
      const center=Math.max(3-wr,wr-4)+Math.max(3-wf,wf-4);
      const dist=Math.abs(wr-sr)+Math.abs(wf-sf);
      const bonus=10*center+4*(14-dist);
      sc+=diff>0?bonus:-bonus;
    }
  }
  // одной лёгкой фигурой без пешек не выиграть
  if(sc>0&&wPawns===0&&wMat<=330) sc=0;
  if(sc<0&&bPawns===0&&bMat<=330) sc=0;
  return (this.side?-sc:sc)+10;
};

// ---------- поиск ----------
function Engine(){
  this.ttKey=new Int32Array(TT_SIZE);
  this.ttMove=new Int32Array(TT_SIZE);
  this.ttScore=new Int32Array(TT_SIZE);
  this.ttDepth=new Int8Array(TT_SIZE);
  this.ttFlag=new Uint8Array(TT_SIZE);
  this.history=new Int32Array(4096);
  this.killers=[];
  for(let i=0;i<MAXPLY+2;i++) this.killers.push([0,0]);
}

Engine.prototype.checkTime=function(){
  if(this.rootDepth>1&&Date.now()>=this.deadline) this.stop=true;
};

Engine.prototype.ttStore=function(pos,depth,score,flag,m,ply){
  const i=pos.hash&TT_MASK;
  if(score>MATE-500) score+=ply; else if(score<-MATE+500) score-=ply;
  this.ttKey[i]=pos.hash; this.ttScore[i]=score; this.ttDepth[i]=depth; this.ttFlag[i]=flag;
  if(m||this.ttKey[i]!==pos.hash) this.ttMove[i]=m;
};

Engine.prototype.order=function(pos,moves,ttm,ply){
  const sc=new Int32Array(moves.length), b=pos.b;
  const k=ply<MAXPLY?this.killers[ply]:[0,0];
  for(let i=0;i<moves.length;i++){
    const m=moves[i], from=mFrom(m), to=mTo(m), v=b[to];
    if(m===ttm) sc[i]=2000000;
    else if(v) sc[i]=1000000+(v&7)*100-(b[from]&7);
    else if(mFlags(m)&F_EP) sc[i]=1000099;
    else if(mPromo(m)) sc[i]=900000+mPromo(m);
    else if(m===k[0]) sc[i]=800000;
    else if(m===k[1]) sc[i]=700000;
    else sc[i]=this.history[from*64+to];
  }
  return sc;
};

function pickNext(moves,sc,i){
  let bi=i;
  for(let j=i+1;j<moves.length;j++) if(sc[j]>sc[bi]) bi=j;
  if(bi!==i){
    const tm=moves[i]; moves[i]=moves[bi]; moves[bi]=tm;
    const ts=sc[i]; sc[i]=sc[bi]; sc[bi]=ts;
  }
}

Engine.prototype.qs=function(pos,alpha,beta,ply){
  if((++this.nodes&1023)===0) this.checkTime();
  if(this.stop) return 0;
  const stand=pos.evaluate();
  if(ply>=MAXPLY) return stand;
  if(stand>=beta) return stand;
  if(stand>alpha) alpha=stand;
  const moves=pos.gen(true), sc=this.order(pos,moves,0,MAXPLY), us=pos.side;
  for(let i=0;i<moves.length;i++){
    pickNext(moves,sc,i);
    const m=moves[i];
    pos.make(m);
    if(pos.attacked(pos.kings[us>>3],pos.side)){ pos.unmake(); continue; }
    const s=-this.qs(pos,-beta,-alpha,ply+1);
    pos.unmake();
    if(this.stop) return 0;
    if(s>alpha){ alpha=s; if(s>=beta) return s; }
  }
  return alpha;
};

Engine.prototype.search=function(pos,depth,alpha,beta,ply,doNull){
  if((++this.nodes&1023)===0) this.checkTime();
  if(this.stop) return 0;
  if(ply>0){
    if(pos.half>=100||pos.isRep()) return 0;
    const ma=-MATE+ply, mb=MATE-ply-1;
    if(alpha<ma) alpha=ma;
    if(beta>mb) beta=mb;
    if(alpha>=beta) return alpha;
  }
  const us=pos.side, inCheck=pos.attacked(pos.kings[us>>3],us^BL);
  if(inCheck) depth++;
  if(depth<=0) return this.qs(pos,alpha,beta,ply);
  if(ply>=MAXPLY) return pos.evaluate();

  const idx=pos.hash&TT_MASK;
  let ttm=0;
  if(this.ttFlag[idx]&&this.ttKey[idx]===pos.hash){
    ttm=this.ttMove[idx];
    if(ply>0&&this.ttDepth[idx]>=depth){
      let s=this.ttScore[idx];
      if(s>MATE-500) s-=ply; else if(s<-MATE+500) s+=ply;
      const fl=this.ttFlag[idx];
      if(fl===TT_EXACT) return s;
      if(fl===TT_LOWER&&s>=beta) return s;
      if(fl===TT_UPPER&&s<=alpha) return s;
    }
  }

  const isPv=beta-alpha>1;
  if(doNull&&!isPv&&!inCheck&&depth>=3&&beta<MATE-500&&pos.hasPieces(us)&&pos.evaluate()>=beta){
    pos.makeNull();
    const s=-this.search(pos,depth-3,-beta,-beta+1,ply+1,false);
    pos.unmakeNull();
    if(this.stop) return 0;
    if(s>=beta) return beta;
  }

  const moves=pos.gen(false), sc=this.order(pos,moves,ttm,ply);
  const kl=this.killers[ply];
  let best=-INF, bestM=0, legal=0;
  const origAlpha=alpha;
  for(let i=0;i<moves.length;i++){
    pickNext(moves,sc,i);
    const m=moves[i];
    const quiet=!pos.b[mTo(m)]&&!(mFlags(m)&F_EP)&&!mPromo(m);
    pos.make(m);
    if(pos.attacked(pos.kings[us>>3],pos.side)){ pos.unmake(); continue; }
    legal++;
    let s;
    if(legal===1){
      s=-this.search(pos,depth-1,-beta,-alpha,ply+1,true);
    }else{
      let red=0;
      if(depth>=3&&legal>3&&quiet&&!inCheck&&m!==kl[0]&&m!==kl[1]&&!pos.attacked(pos.kings[pos.side>>3],us))
        red=legal>8?2:1;
      s=-this.search(pos,depth-1-red,-alpha-1,-alpha,ply+1,true);
      if(s>alpha&&red) s=-this.search(pos,depth-1,-alpha-1,-alpha,ply+1,true);
      if(s>alpha&&s<beta) s=-this.search(pos,depth-1,-beta,-alpha,ply+1,true);
    }
    pos.unmake();
    if(this.stop) return 0;
    if(s>best){
      best=s; bestM=m;
      if(s>alpha){
        alpha=s;
        if(s>=beta){
          if(quiet){
            if(kl[0]!==m){ kl[1]=kl[0]; kl[0]=m; }
            this.history[mFrom(m)*64+mTo(m)]+=depth*depth;
          }
          break;
        }
      }
    }
  }
  if(!legal) return inCheck?-MATE+ply:0;
  this.ttStore(pos,depth,best,best>=beta?TT_LOWER:best>origAlpha?TT_EXACT:TT_UPPER,bestM,ply);
  return best;
};

Engine.prototype.pv=function(pos,first,maxLen){
  const line=[first];
  pos.make(first);
  let n=1;
  while(n<maxLen){
    const i=pos.hash&TT_MASK;
    if(!this.ttFlag[i]||this.ttKey[i]!==pos.hash||!this.ttMove[i]) break;
    const m=this.ttMove[i];
    if(!pos.legal().includes(m)) break;
    if(pos.isRep()) break;
    line.push(m); pos.make(m); n++;
  }
  for(let j=0;j<n;j++) pos.unmake();
  return line;
};

// итеративное углубление с несколькими вариантами (multipv)
Engine.prototype.think=function(pos,timeMs,multipv,onInfo,maxDepth){
  const start=Date.now();
  this.deadline=start+timeMs; this.stop=false; this.nodes=0;
  for(let i=0;i<4096;i++) this.history[i]>>=2;
  const root=pos.legal();
  if(!root.length) return null;
  let order=root.map(m=>({m,score:0}));
  let result=null;
  for(let d=1;d<=(maxDepth||60);d++){
    this.rootDepth=d;
    const k=Math.min(multipv,order.length);
    const res=[];
    for(let i=0;i<order.length;i++){
      const m=order[i].m;
      let alpha=-INF;
      if(res.length>=k){ const sorted=res.map(x=>x.score).sort((a,b)=>b-a); alpha=sorted[k-1]; }
      pos.make(m);
      let s;
      if(alpha===-INF) s=-this.search(pos,d-1,-INF,INF,1,true);
      else{
        s=-this.search(pos,d-1,-alpha-1,-alpha,1,true);
        if(!this.stop&&s>alpha) s=-this.search(pos,d-1,-INF,-alpha,1,true);
      }
      pos.unmake();
      if(this.stop) break;
      res.push({m,score:s});
    }
    if(this.stop) break;
    res.sort((a,b)=>b.score-a.score);
    order=res;
    result={
      depth:d, nodes:this.nodes, time:Date.now()-start,
      lines:res.slice(0,k).map(x=>({m:x.m, score:x.score, pv:this.pv(pos,x.m,Math.min(d+4,14))}))
    };
    if(onInfo) onInfo(result);
    const top=Math.abs(res[0].score);
    if(root.length===1&&d>=4) break;
    if(top>MATE-500&&d>=(MATE-top)+2) break;
    if(Date.now()-start>timeMs*0.55) break;
  }
  return result;
};

// запуск внутри Web Worker
if(typeof importScripts==="function"){
  const engine=new Engine();
  self.onmessage=e=>{
    const {id,fen,moves,time,multipv,maxDepth}=e.data;
    const pos=new Pos().load(fen);
    for(const m of moves) pos.make(m);
    const res=engine.think(pos,time,multipv,info=>postMessage({type:"info",id,info}),maxDepth);
    postMessage({type:"done",id,info:res});
  };
}
return {Pos, Engine, mFrom, mTo, sqName, MATE, BL};
};
const E=engineFactory();

const SITE=location.hostname.includes("lichess")?"lichess":"chesscom";
const TYPES={p:1,n:2,b:3,r:4,q:5,k:6};
const LICHESS_TYPES={pawn:1,knight:2,bishop:3,rook:4,queen:5,king:6};
const GLYPH=["","♙","♘","♗","♖","♕","♔"];

// ---------- только партии против ботов ----------
function isBotGame(){
  if(SITE==="chesscom") return /^\/play\/computer/.test(location.pathname);
  // lichess: соперник сверху — Stockfish (у ИИ нет рейтинга)
  const top=document.querySelector(".round__app .ruser-top");
  return !!top&&/stockfish/i.test(top.textContent)&&!top.querySelector("rating");
}

// ---------- чтение доски ----------
// grid: индекс 0 = a8, 63 = h1; значение = тип | цвет (BL для чёрных)
function idx(file,rank){ return (7-rank)*8+file; }  // file, rank: 0..7

function readChessCom(){
  const el=document.querySelector("wc-chess-board, chess-board");
  if(!el) return null;
  const grid=new Array(64).fill(0);
  const sqOf=node=>{
    const c=[...node.classList].find(x=>/^square-\d\d$/.test(x));
    return c?idx(+c[7]-1,+c[8]-1):-1;
  };
  el.querySelectorAll(".piece").forEach(p=>{
    const s=sqOf(p), pc=[...p.classList].find(x=>/^[wb][pnbrqk]$/.test(x));
    if(s<0||!pc) return;
    grid[s]=TYPES[pc[1]]|(pc[0]==="b"?E.BL:0);
  });
  const last=[...el.querySelectorAll(".highlight")].map(sqOf).filter(s=>s>=0);
  return {el, grid, flipped:el.classList.contains("flipped"), last};
}

function readLichess(){
  const board=document.querySelector(".round__app cg-board");
  if(!board) return null;
  const wrap=board.closest(".cg-wrap");
  const flipped=!!wrap&&wrap.classList.contains("orientation-black");
  const size=board.offsetWidth/8;
  const sqOf=node=>{
    if(node.cgKey) return idx(node.cgKey.charCodeAt(0)-97,+node.cgKey[1]-1);
    const m=(node.style.transform||"").match(/translate\(\s*([\d.]+)px\s*,\s*([\d.]+)px/);
    if(!m||!size) return -1;
    const col=Math.round(+m[1]/size), row=Math.round(+m[2]/size);
    return flipped?idx(7-col,row):idx(col,7-row);
  };
  const grid=new Array(64).fill(0);
  board.querySelectorAll("piece").forEach(p=>{
    if(p.classList.contains("ghost")||p.classList.contains("fading")) return;
    const s=sqOf(p);
    const t=[...p.classList].map(c=>LICHESS_TYPES[c]).find(Boolean);
    if(s<0||!t) return;
    grid[s]=t|(p.classList.contains("black")?E.BL:0);
  });
  const last=[...board.querySelectorAll("square.last-move")].map(sqOf).filter(s=>s>=0);
  return {el:board, grid, flipped, last};
}

// Позиция в FEN. Очередь хода определяем по подсветке последнего хода,
// рокировки — по королям и ладьям на исходных полях.
function toFen(st){
  const g=st.grid;
  let rows=[];
  for(let r=0;r<8;r++){
    let s="", e=0;
    for(let f=0;f<8;f++){
      const p=g[r*8+f];
      if(!p){ e++; continue; }
      if(e){ s+=e; e=0; }
      const ch=" pnbrqk"[p&7];
      s+=(p&E.BL)?ch:ch.toUpperCase();
    }
    rows.push(s+(e||""));
  }
  let side="w", ep="-";
  const moved=st.last.filter(s=>g[s]);
  if(moved.length){
    const to=moved[0], p=g[to];
    side=(p&E.BL)?"w":"b";
    const from=st.last.find(s=>s!==to);
    if((p&7)===1&&from!==undefined&&(from&7)===(to&7)&&Math.abs(from-to)===16) ep=E.sqName((from+to)>>1);
  }
  let c="";
  if(g[60]===6){ if(g[63]===4) c+="K"; if(g[56]===4) c+="Q"; }
  if(g[4]===(6|E.BL)){ if(g[7]===(4|E.BL)) c+="k"; if(g[0]===(4|E.BL)) c+="q"; }
  return rows.join("/")+" "+side+" "+(c||"-")+" "+ep+" 0 1";
}

// ---------- интерфейс ----------
const settings={on:true, time:1000};
try{ Object.assign(settings,JSON.parse(localStorage.getItem("chessArrows")||"{}")); }catch(e){}
function save(){ try{ localStorage.setItem("chessArrows",JSON.stringify(settings)); }catch(e){} }

const NS="http://www.w3.org/2000/svg";
const svg=document.createElementNS(NS,"svg");
svg.setAttribute("viewBox","0 0 8 8");
svg.style.cssText="position:fixed;pointer-events:none;z-index:99999;display:none";
svg.innerHTML=`<defs>
  <marker id="rd-ah0" markerWidth="4" markerHeight="4" refX="2" refY="2" orient="auto"><path d="M0,0 L4,2 L0,4 z" fill="rgba(30,200,90,.9)"/></marker>
  <marker id="rd-ah1" markerWidth="4" markerHeight="4" refX="2" refY="2" orient="auto"><path d="M0,0 L4,2 L0,4 z" fill="rgba(60,140,255,.7)"/></marker>
</defs><g id="rd-lines"></g>`;

const panel=document.createElement("div");
panel.style.cssText="position:fixed;right:12px;bottom:12px;z-index:99999;background:#200000ee;color:#fff;"+
  "font:14px Arial,sans-serif;padding:8px 12px;border-radius:10px;box-shadow:0 4px 16px #0008;min-width:170px;display:none";
panel.innerHTML=`<div style="display:flex;justify-content:space-between;gap:8px;align-items:center">
  <b>♟ Помощник</b>
  <button id="rd-toggle" style="border:none;border-radius:6px;padding:2px 8px;color:#fff;cursor:pointer"></button>
</div>
<div id="rd-info" style="margin-top:6px"></div>
<div style="margin-top:6px;font-size:12px;color:#ccc">Расчёт:
  <select id="rd-time"><option value="500">0.5 с</option><option value="1000">1 с</option><option value="2000">2 с</option><option value="4000">4 с</option></select>
  · Alt+A — вкл/выкл</div>`;

function mount(){
  if(!svg.isConnected) document.body.appendChild(svg);
  if(!panel.isConnected){
    document.body.appendChild(panel);
    panel.querySelector("#rd-toggle").onclick=toggle;
    const sel=panel.querySelector("#rd-time");
    sel.value=String(settings.time);
    sel.onchange=()=>{ settings.time=+sel.value; save(); lastFen=""; tick(); };
  }
  const t=panel.querySelector("#rd-toggle");
  t.textContent=settings.on?"вкл":"выкл";
  t.style.background=settings.on?"#2e8b57":"#777";
}

function toggle(){
  settings.on=!settings.on; save();
  lastFen=""; clearArrows(); setInfo(settings.on?"":"выключен");
  mount(); tick();
}
document.addEventListener("keydown",e=>{ if(e.altKey&&(e.code==="KeyA")){ e.preventDefault(); if(isBotGame()) toggle(); } });

function setInfo(html){ const el=panel.querySelector("#rd-info"); if(el) el.innerHTML=html; }

function fmt(sc){
  if(sc>E.MATE-500) return "мат в "+Math.ceil((E.MATE-sc)/2);
  if(sc<-E.MATE+500) return "вам мат в "+Math.ceil((E.MATE+sc)/2);
  return (sc>0?"+":"")+(sc/100).toFixed(2);
}

let arrowState=null;  // {el, flipped, moves:[m...]}

function clearArrows(){ arrowState=null; svg.style.display="none"; svg.querySelector("#rd-lines").innerHTML=""; }

function placeOverlay(){
  if(!arrowState||!arrowState.el.isConnected){ svg.style.display="none"; return; }
  const r=arrowState.el.getBoundingClientRect();
  Object.assign(svg.style,{left:r.left+"px",top:r.top+"px",width:r.width+"px",height:r.height+"px",display:"block"});
}

function drawArrows(st,lines){
  const g=svg.querySelector("#rd-lines");
  g.innerHTML="";
  const xy=s=>{ const f=s&7, r=s>>3; return st.flipped?[7-f+.5,7-r+.5]:[f+.5,r+.5]; };
  lines.slice(0,2).reverse().forEach((ln,i,arr)=>{
    const main=i===arr.length-1;
    const [x1,y1]=xy(E.mFrom(ln.m)), [x2,y2]=xy(E.mTo(ln.m));
    const len=Math.hypot(x2-x1,y2-y1), k=(len-.45)/len;
    const l=document.createElementNS(NS,"line");
    l.setAttribute("x1",x1); l.setAttribute("y1",y1);
    l.setAttribute("x2",x1+(x2-x1)*k); l.setAttribute("y2",y1+(y2-y1)*k);
    l.setAttribute("stroke",main?"rgba(30,200,90,.9)":"rgba(60,140,255,.6)");
    l.setAttribute("stroke-width",main?".18":".12");
    l.setAttribute("stroke-linecap","round");
    l.setAttribute("marker-end","url(#"+(main?"rd-ah0":"rd-ah1")+")");
    g.appendChild(l);
  });
  arrowState={el:st.el, flipped:st.flipped};
  placeOverlay();
}

// ---------- расчёт ----------
let worker=null, workerBroken=false, searchId=0, lastFen="";

function getWorker(){
  if(worker||workerBroken) return worker;
  try{
    const url=URL.createObjectURL(new Blob(["("+engineFactory.toString()+")();"],{type:"application/javascript"}));
    worker=new Worker(url);
    worker.onerror=()=>{ worker=null; workerBroken=true; lastFen=""; tick(); };
  }catch(e){ worker=null; workerBroken=true; }
  return worker;
}

function stop(){
  searchId++;
  if(worker){ worker.terminate(); worker=null; }
}

function analyze(fen,st){
  stop();
  const id=searchId;
  const show=info=>{
    if(id!==searchId||!info) return;
    drawArrows(st,info.lines);
    const l=info.lines[0], piece=st.grid[E.mFrom(l.m)]&7;
    setInfo(`<span style="font-size:18px;color:#7dff9b">${GLYPH[piece]} ${E.sqName(E.mFrom(l.m))}→${E.sqName(E.mTo(l.m))}</span>`+
      ` <span>${fmt(l.score)}</span><br><span style="font-size:12px;color:#aaa">глубина ${info.depth}</span>`);
  };
  setInfo("думаю…");
  const w=getWorker();
  if(w){
    w.onmessage=e=>show(e.data.info);
    w.postMessage({id,fen,moves:[],time:settings.time,multipv:2});
  }else{
    // CSP сайта не дал создать Worker — считаем прямо на странице, но покороче
    setTimeout(()=>{
      if(id!==searchId) return;
      const pos=new E.Pos().load(fen);
      show(new E.Engine().think(pos,Math.min(settings.time,800),2));
    },20);
  }
}

function tick(){
  if(!isBotGame()){ panel.style.display="none"; clearArrows(); stop(); lastFen=""; return; }
  mount();
  panel.style.display="block";
  if(!settings.on) return;
  const st=SITE==="lichess"?readLichess():readChessCom();
  if(!st){ setInfo("доска не найдена"); clearArrows(); return; }
  const fen=toFen(st);
  if(fen===lastFen){ placeOverlay(); return; }
  lastFen=fen;
  let pos;
  try{ pos=new E.Pos().load(fen); }catch(e){ clearArrows(); setInfo("не могу прочитать позицию"); return; }
  const mine=st.flipped?E.BL:0;
  if(!pos.legal().length){ stop(); clearArrows(); setInfo("партия окончена"); return; }
  if(pos.side!==mine){ stop(); clearArrows(); setInfo("ход бота…"); return; }
  analyze(fen,st);
}

let timer=0;
const schedule=()=>{ clearTimeout(timer); timer=setTimeout(tick,250); };
new MutationObserver(recs=>{
  // свои стрелки и панель не считаются изменением доски
  if(recs.some(r=>!svg.contains(r.target)&&!panel.contains(r.target))) schedule();
}).observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:["class","style"]});
window.addEventListener("resize",placeOverlay);
window.addEventListener("scroll",placeOverlay,true);
setInterval(()=>{ placeOverlay(); schedule(); },1500);
tick();
})();
