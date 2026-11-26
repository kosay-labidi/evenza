/* Mes événements — scène 3D. Amélioration progressive : sans JS la page reste une grille de cartes cliquables. */
(function(){
  var root=document.getElementById('es'), rail=document.getElementById('es-rail'); if(!root||!rail) return;
  var all=[].slice.call(rail.querySelectorAll('.es-card')), panels=[].slice.call(document.querySelectorAll('.es-panel'));
  var pid=0, filt='ALL', cur=0, drag=0, down=false, moved=false, x0=0, keyboardFocus=false, items=all.slice(), reduce=matchMedia('(prefers-reduced-motion:reduce)').matches;
  root.classList.add('es-ready');
  if(reduce) root.classList.add('es-reduced-motion');
  ['es-filters','es-views','es-k','es-prev','es-next'].forEach(function(id){var n=document.getElementById(id); if(n) n.hidden=false;});
  var bgs=[root.querySelector('.es-bg-a'),root.querySelector('.es-bg-b')], bgi=0, lastBg='';
  function setBg(c){ if(!c||c.dataset.img===lastBg) return; lastBg=c.dataset.img; var a=bgs[bgi]; a.style.backgroundImage='url("'+c.dataset.img+'")'; a.classList.add('on'); bgs[1-bgi].classList.remove('on'); bgi=1-bgi; }
  function mob(){return innerWidth<900;}
  function layout(){
    var w=mob()?Math.min(250,innerWidth*.64):290, h=Math.round(w*1.34);
    rail.style.setProperty('--cw',w+'px'); rail.style.setProperty('--ch',h+'px'); rail.style.setProperty('--rh',(h+52)+'px');
    var p=cur-drag/(w*.9);
    items.forEach(function(c,i){
      var d=i-p, a=Math.abs(d), x=d*w*(reduce ? .92 : (mob() ? .62 : 1.04)), rot=reduce ? 0 : Math.max(-46,Math.min(46,-d*36)), z=reduce ? 0 : -Math.min(a,3)*80+(a<.5?90:0), sc=reduce ? 1 : Math.max(.5,1.04-Math.min(a,3)*.17);
      c.style.transform='translateX('+x+'px) translateZ('+z+'px) rotateY('+rot+'deg) scale('+sc+')';
      c.style.opacity=a>2.7?0:1; c.style.filter='brightness('+(1-Math.min(a,2)*.3)+')'; c.style.zIndex=100-Math.round(a*10);
      c.style.pointerEvents=a>2.7?'none':'auto'; c.classList.toggle('act',Math.round(a)===0);
      c.setAttribute('aria-label',(c.dataset.title||'Événement')+', '+(i+1)+' sur '+items.length);
      c.setAttribute('aria-current',i===cur?'true':'false');
    });
    var k=Math.round(Math.min(items.length-1,Math.max(0,p)));
    [].forEach.call(document.querySelectorAll('#es-dots .es-dot'),function(d,i){d.setAttribute('aria-current',i===k?'true':'false');});
    var cnt=document.getElementById('es-cnt'); if(cnt){ cnt.textContent=items.length?('0'+(k+1)).slice(-2)+' / '+('0'+items.length).slice(-2):''; cnt.setAttribute('aria-label',items.length?'Événement '+(k+1)+' sur '+items.length:'Aucun événement'); }
    var prev=document.getElementById('es-prev'), next=document.getElementById('es-next');
    if(prev) prev.disabled=cur<=0; if(next) next.disabled=cur>=items.length-1;
  }
  function showPanel(){
    var c=items[cur]; panels.forEach(function(p){p.hidden=!(c&&p.dataset.i===c.dataset.i);});
    var p=c&&panels.filter(function(x){return x.dataset.i===c.dataset.i;})[0]; if(!p) return;
    var C=326.7, pct=+(p.querySelector('.es-ring').dataset.pct||0), v=p.querySelector('.es-ring .v');
    v.style.strokeDashoffset=C; requestAnimationFrame(function(){requestAnimationFrame(function(){v.style.strokeDashoffset=C*(1-Math.min(100,pct)/100);});});
    if(!reduce){ var t0=performance.now(); [].forEach.call(p.querySelectorAll('[data-n]'),function(el){var n=+el.dataset.n,s=el.dataset.s||'';
      (function f(t){var k=Math.min(1,(t-t0)/800); el.textContent=Math.round(n*(1-Math.pow(1-k,3))).toLocaleString('fr-FR')+s; if(k<1) requestAnimationFrame(f);})(t0);}); }
    tick();
  }
  function go(i){ if(!items.length){ panels.forEach(function(p){p.hidden=true;}); layout(); return; } cur=Math.min(items.length-1,Math.max(0,i)); drag=0; layout(); setBg(items[cur]); showPanel(); }
  function dots(){ var d=document.getElementById('es-dots'); d.innerHTML=''; items.forEach(function(c,i){var b=document.createElement('button'); b.type='button'; b.className='es-dot'; b.setAttribute('aria-label','Afficher '+(c.dataset.title||'événement')+', '+(i+1)+' sur '+items.length); b.setAttribute('aria-current',i===cur?'true':'false'); b.innerHTML='<span aria-hidden="true"></span>'; b.onclick=function(){go(i);}; d.appendChild(b);}); }
  /* glisser / swipe */
  document.addEventListener('keydown',function(e){if(e.key==='Tab') keyboardFocus=true;},true);
  document.addEventListener('pointerdown',function(){keyboardFocus=false;},true);
  rail.addEventListener('pointerdown',function(e){ if(root.classList.contains('es-mos')) return; down=true; moved=false; x0=e.clientX; pid=e.pointerId; });
  rail.addEventListener('pointermove',function(e){
    if(down){ drag=e.clientX-x0; if(!moved&&Math.abs(drag)>6){ moved=true; rail.classList.add('drag'); try{rail.setPointerCapture(pid);}catch(_){} } layout(); return; }
    if(reduce) return;
    var c=items[cur]; if(!c||root.classList.contains('es-mos')) return; var r=c.getBoundingClientRect(), px=(e.clientX-r.left)/r.width, py=(e.clientY-r.top)/r.height;
    if(px<0||px>1||py<0||py>1){ c.style.removeProperty('--rx'); c.style.removeProperty('--ry'); return; }
    c.style.setProperty('--ry',((px-.5)*16).toFixed(1)+'deg'); c.style.setProperty('--rx',((.5-py)*12).toFixed(1)+'deg'); c.style.setProperty('--gx',px*100+'%'); c.style.setProperty('--gy',py*100+'%');
  });
  function up(){ if(!down) return; down=false; rail.classList.remove('drag'); var w=items[0]?items[0].offsetWidth:290; if(moved) go(Math.round(cur-drag/(w*.9))); else drag=0, layout(); }
  rail.addEventListener('pointerup',up); rail.addEventListener('pointercancel',up);
  /* un clic ne suit le lien que sur la carte centrale (les autres la mettent au centre) */
  rail.addEventListener('click',function(e){
    var link=e.target.closest('.es-card-link'), c=link&&link.closest('.es-card'); if(!c) return;
    if(moved){ e.preventDefault(); moved=false; return; }
    if(root.classList.contains('es-mos')) return;
    var i=items.indexOf(c); if(i!==cur){ e.preventDefault(); go(i); }
  });
  rail.addEventListener('focusin',function(e){
    if(!keyboardFocus||root.classList.contains('es-mos')) return;
    var c=e.target.closest('.es-card-link,.es-b3'); if(!c) return;
    var card=c.closest('.es-card'), i=items.indexOf(card); if(i>=0&&i!==cur) go(i);
  });
  rail.addEventListener('keydown',function(e){
    if(e.key==='ArrowRight'){e.preventDefault();go(cur+1);}
    else if(e.key==='ArrowLeft'){e.preventDefault();go(cur-1);}
    else if(e.key==='Home'){e.preventDefault();go(0);}
    else if(e.key==='End'){e.preventDefault();go(items.length-1);}
  });
  document.getElementById('es-prev').onclick=function(){go(cur-1);}; document.getElementById('es-next').onclick=function(){go(cur+1);};
  if(!reduce) document.addEventListener('pointermove',function(e){ var r=root.getBoundingClientRect(); root.querySelector('.es-spot').style.setProperty('--sx',(e.clientX-r.left)+'px'); root.querySelector('.es-spot').style.setProperty('--sy',(e.clientY-r.top)+'px'); });
  /* filtres */
  var fb=[].slice.call(document.querySelectorAll('#es-filters [data-f]'));
  function keep(c){ return filt==='ARCH'?c.dataset.archived==='1':(c.dataset.archived!=='1'&&(filt==='ALL'||c.dataset.st===filt)); }
  function counts(){ fb.forEach(function(b){ var n=all.filter(function(c){ var a=c.dataset.archived==='1'; return b.dataset.f==='ARCH'?a:(!a&&(b.dataset.f==='ALL'||c.dataset.st===b.dataset.f)); }).length; b.querySelector('em').textContent=n; }); }
  counts();
  function apply(){ counts(); items=all.filter(keep); all.forEach(function(c){c.hidden=items.indexOf(c)<0;}); fb.forEach(function(b){b.setAttribute('aria-pressed',b.dataset.f===filt);}); cur=0; dots(); go(0); }
  fb.forEach(function(b){ b.onclick=function(){filt=b.dataset.f; apply();}; });
  /* vues */
  [].forEach.call(document.querySelectorAll('#es-views [data-v]'),function(b){ b.onclick=function(){
    var mos=b.dataset.v==='mos'; root.classList.toggle('es-mos',mos);
    [].forEach.call(document.querySelectorAll('#es-views [data-v]'),function(x){x.setAttribute('aria-pressed',x===b);});
    all.forEach(function(c){c.style.cssText=''; }); if(!mos) go(cur); }; });
  /* onglets */
  document.getElementById('es-details').addEventListener('click',function(e){ var t=e.target.closest('[data-t]'); if(!t) return; var p=t.closest('.es-panel');
    [].forEach.call(p.querySelectorAll('[data-t]'),function(b){b.setAttribute('aria-selected',b===t);b.tabIndex=b===t?0:-1;});
    [].forEach.call(p.querySelectorAll('[data-pane]'),function(x){x.hidden=x.dataset.pane!==t.dataset.t;}); });
  document.getElementById('es-details').addEventListener('keydown',function(e){
    var t=e.target.closest('[role="tab"][data-t]'); if(!t) return;
    var p=t.closest('.es-panel'), tabs=[].slice.call(p.querySelectorAll('[role="tab"][data-t]')), i=tabs.indexOf(t), n=i;
    if(e.key==='ArrowRight') n=(i+1)%tabs.length;
    else if(e.key==='ArrowLeft') n=(i-1+tabs.length)%tabs.length;
    else if(e.key==='Home') n=0;
    else if(e.key==='End') n=tabs.length-1;
    else return;
    e.preventDefault(); tabs[n].focus(); tabs[n].click();
  });
  /* compte à rebours */
  function tick(){ var p=panels.filter(function(x){return !x.hidden;})[0]; if(!p) return; var cd=p.querySelector('[data-cd]'); if(!cd) return;
    var ms=Math.max(0,new Date(p.dataset.start)-new Date()), v=[Math.floor(ms/864e5),Math.floor(ms/36e5)%24,Math.floor(ms/6e4)%60,Math.floor(ms/1e3)%60];
    [].forEach.call(cd.children,function(d,i){d.firstChild.textContent=i?('0'+v[i]).slice(-2):v[i];}); }
  setInterval(tick,1000);
  /* recherche rapide Ctrl/⌘ K */
  var K=document.getElementById('es-cmdk'), q=document.getElementById('es-cq'), L=document.getElementById('es-cl'), sel=0, res=[];
  function draw(){ var s=q.value.trim().toLowerCase(); res=all.filter(function(c){return !s||(c.dataset.title+' '+c.dataset.sub).toLowerCase().indexOf(s)>=0;}); sel=Math.min(sel,Math.max(0,res.length-1));
    L.innerHTML=''; if(!res.length){L.innerHTML='<p>Aucun résultat</p>';return;}
    res.forEach(function(c,i){var a=document.createElement('a'); a.href='#'; a.setAttribute('aria-selected',i===sel); a.innerHTML='<i></i><span><b></b><small></small></span>';
      a.querySelector('i').style.backgroundImage='url("'+c.dataset.img+'")'; a.querySelector('b').textContent=c.dataset.title; a.querySelector('small').textContent=c.dataset.sub;
      a.onclick=function(e){e.preventDefault(); pick(c);}; L.appendChild(a);}); }
  function pick(c){ K.hidden=true; filt=c.dataset.archived==='1'?'ARCH':'ALL'; root.classList.remove('es-mos'); apply(); go(items.indexOf(c)); }
  function open(){ K.hidden=false; q.value=''; sel=0; draw(); q.focus(); } function close(){ K.hidden=true; }
  var kb=document.getElementById('es-k'); if(kb) kb.onclick=open; K.onclick=function(e){if(e.target===K) close();};
  q.addEventListener('input',function(){sel=0;draw();});
  document.addEventListener('keydown',function(e){
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){ e.preventDefault(); K.hidden?open():close(); return; }
    if(K.hidden) return;
    if(e.key==='Escape') close(); if(e.key==='ArrowDown'){e.preventDefault(); sel=Math.min(res.length-1,sel+1); draw();} if(e.key==='ArrowUp'){e.preventDefault(); sel=Math.max(0,sel-1); draw();}
    if(e.key==='Enter'&&res[sel]){e.preventDefault(); pick(res[sel]);} });
  if(/Mac|iPhone|iPad/.test(navigator.platform||'')&&kb) kb.querySelector('kbd').textContent='⌘ K';
  addEventListener('resize',layout);
  /* départ : prochain événement à venir, sinon le premier */
  var now=new Date(), start=0; for(var i=0;i<all.length;i++){ if(new Date(all[i].dataset.start)>=now){ start=i; break; } }
  apply(); var k0=items.indexOf(all[start]); go(k0<0?0:k0);
  window.__es={apply:apply,all:all,go:go,current:function(){return items[cur];}};
})();

/* ---------- Aperçu 3D, likes, commentaires, rooms ---------- */
(function(){
  var box=document.getElementById('es-ap'); if(!box||!window.__es) return;
  var $=function(id){return document.getElementById(id);}, csrf=$('es-csrf').value, D=null, pk=0, mode='room', rid=0, last=0, timer=null, lastFocus=null;
  function el(t,c,x){ var n=document.createElement(t); if(c) n.className=c; if(x!=null) n.textContent=x; return n; }
  function api(url,post,body){
    var o={credentials:'same-origin',headers:{'X-Requested-With':'fetch'}};
    if(post){ o.method='POST'; o.headers['X-CSRFToken']=csrf; o.headers['Content-Type']='application/x-www-form-urlencoded'; o.body=new URLSearchParams(body||{}).toString(); }
    return fetch(url,o).then(function(r){ return r.json().then(function(j){ if(!r.ok) throw new Error(j.erreur||'Erreur'); return j; }); });
  }
  var U=function(path){ return '/social/evenement/'+pk+'/'+path; };
  /* --- ouverture / fermeture --- */
  function open(id){
    pk=id; lastFocus=document.activeElement; box.hidden=false; document.body.style.overflow='hidden'; $('es-ap-x').focus();
    $('es-ap-t').textContent='…'; $('es-sum').textContent='Chargement…';
    api(U('apercu/')).then(function(d){ D=d; render(); }).catch(function(e){ $('es-sum').textContent='Aperçu indisponible : '+e.message; });
  }
  function close(){ box.hidden=true; document.body.style.overflow=''; clearInterval(timer); if(lastFocus) lastFocus.focus(); }
  $('es-ap-x').onclick=close; box.addEventListener('click',function(e){ if(e.target===box) close(); });
  document.addEventListener('keydown',function(e){ if(!box.hidden&&e.key==='Escape'){ e.stopPropagation(); close(); } },true);
  document.addEventListener('click',function(e){
    var b=e.target.closest('[data-open-apercu]'); if(!b) return; e.preventDefault(); e.stopPropagation();
    var c=b.closest('.es-card'); open(+(b.dataset.pk||(c&&c.dataset.pk)));
  },true);
  /* --- rendu --- */
  function render(){
    $('es-ap-t').textContent=D.titre;
    $('es-ai').textContent=D.source==='ia'?'Résumé généré par IA':'Résumé automatique';
    $('es-sum').textContent=D.resume;
    var lg=$('es-legend'); lg.innerHTML=''; D.plan.forEach(function(z,i){ var li=el('li'); li.appendChild(el('b','',i+1)); li.appendChild(document.createTextNode(z.label)); lg.appendChild(li); });
    var t=$('es-tags'); t.innerHTML=''; D.tags.forEach(function(x){ t.appendChild(el('span','',x)); });
    social(D.etat); scene(D.plan);
    var r=$('es-rooms'); r.innerHTML='';
    D.rooms.forEach(function(x){ var b=el('button','', '#'+x.nom); b.type='button'; b.dataset.r=x.id; b.setAttribute('aria-pressed','false'); b.onclick=function(){ pickRoom(x.id); }; r.appendChild(b); });
    setMode('room'); pickRoom(D.rooms[0].id);
    clearInterval(timer); timer=setInterval(poll,4000);
  }
  function social(s){
    $('es-likes').textContent=s.likes; $('es-ncom').textContent=s.commentaires;
    [].forEach.call(document.querySelectorAll('#es-soc [data-k]'),function(b){ var on=b.dataset.k==='LIKE'?s.aime:b.dataset.k==='SAVE'?s.enregistre:s.archive; b.setAttribute('aria-pressed',on); });
  }
  $('es-soc').addEventListener('click',function(e){
    var b=e.target.closest('[data-k]'); if(!b) return;
    api(U('basculer/'+b.dataset.k+'/'),true).then(function(s){ D.etat=s; social(s);
      var c=document.querySelector('.es-card[data-pk="'+pk+'"]'); if(c&&b.dataset.k==='ARCHIVE'){ c.dataset.archived=s.archive?'1':''; window.__es.apply(); }
    });
  });
  $('es-share').onclick=function(){
    var url=location.origin+'/evenements/'+pk+'/', b=$('es-share');
    var done=function(m){ b.lastChild.textContent=m; setTimeout(function(){ b.lastChild.textContent='Partager'; },1800); };
    if(navigator.share){ navigator.share({title:D.titre,url:url}).catch(function(){}); }
    else if(navigator.clipboard){ navigator.clipboard.writeText(url).then(function(){ done('Lien copié'); },function(){ done(url); }); } else done(url);
  };
  /* --- commentaires et rooms --- */
  function setMode(m){ mode=m; [].forEach.call(box.querySelectorAll('.es-aps [data-s]'),function(b){ b.setAttribute('aria-selected',b.dataset.s===m); });
    $('es-rooms').hidden=m!=='room'; $('es-in').placeholder=m==='room'?'Écrire dans la room…':'Ajouter un commentaire…'; }
  box.querySelector('.es-aps .es-tabs').addEventListener('click',function(e){ var b=e.target.closest('[data-s]'); if(!b) return; setMode(b.dataset.s); if(b.dataset.s==='com') loadCom(); else pickRoom(rid||D.rooms[0].id); });
  function msgNode(m,isCom){
    var w=el('div','es-m'+(m.orga?' orga':'')), a=el('div','av',(m.auteur||'?').charAt(0).toUpperCase()), c=el('div'), h=el('div');
    h.appendChild(el('b','',m.auteur)); if(m.orga) h.appendChild(el('span','bd','Orga')); h.appendChild(el('small','',m.heure||m.date));
    if(isCom&&m.supprimable){ var d=el('button','del','Supprimer'); d.type='button'; d.onclick=function(){ api(U('commentaires/'+m.id+'/supprimer/'),true).then(loadCom); }; h.appendChild(d); }
    c.appendChild(h); c.appendChild(el('p','',m.texte)); w.appendChild(a); w.appendChild(c); return w;
  }
  function feedFill(nodes,empty){ var f=$('es-feed'), bas=f.scrollHeight-f.scrollTop-f.clientHeight<40; nodes.forEach(function(n){ f.appendChild(n); }); if(!f.children.length) f.appendChild(el('p','es-none',empty)); else { var e0=f.querySelector('.es-none'); if(e0&&nodes.length) e0.remove(); } if(bas) f.scrollTop=f.scrollHeight; }
  function loadCom(){ api(U('commentaires/')).then(function(j){ $('es-ncom').textContent=j.total; var f=$('es-feed'); f.innerHTML=''; feedFill(j.liste.map(function(c){return msgNode(c,true);}),'Aucun commentaire pour le moment.'); }); }
  function pickRoom(id){ rid=id; last=0; [].forEach.call(document.querySelectorAll('#es-rooms [data-r]'),function(b){ b.setAttribute('aria-pressed',+b.dataset.r===id); }); $('es-feed').innerHTML=''; poll(true); }
  function poll(first){
    if(mode!=='room'||!rid||box.hidden) return;
    api(U('rooms/'+rid+'/messages/?apres='+last)).then(function(j){ if(j.messages.length) last=j.messages[j.messages.length-1].id; feedFill(j.messages.map(function(m){return msgNode(m,false);}),'Aucun message. Lancez la discussion !'); });
  }
  $('es-send').addEventListener('submit',function(e){
    e.preventDefault(); var i=$('es-in'), t=i.value.trim(); if(!t) return; i.value='';
    if(mode==='com') api(U('commentaires/'),true,{texte:t}).then(loadCom).catch(function(x){ i.value=t; });
    else api(U('rooms/'+rid+'/messages/?apres='+last),true,{texte:t}).then(function(j){ if(j.messages.length) last=j.messages[j.messages.length-1].id; feedFill(j.messages.map(function(m){return msgNode(m,false);}),''); }).catch(function(){ i.value=t; });
  });
  /* --- maquette 3D --- */
  var CAM={ens:[57,-36,1],face:[70,0,1.05],top:[8,0,.85]}, small=function(){return innerWidth<900?.62:1;}, cx=57, cz=-36, zs=1, pins=[], raf=0;
  function setCam(a,b,z){ cx=a; cz=b; zs=z; applyCam(); }
  function applyCam(){ var w=$('es-world'); w.style.setProperty('--cx',cx+'deg'); w.style.setProperty('--cz',cz+'deg'); w.style.setProperty('--zs',zs); trackPins(); }
  function scene(plan){
    var fl=$('es-floor'); fl.innerHTML=''; pins=[]; $('es-pins').innerHTML=''; var n=0;
    plan.forEach(function(z){
      var d=el('div','es-z '+(z.t==='stage'?'stage':z.t)+(z.hi?' hi':'')); d.style.cssText='left:'+z.x+'px;top:'+z.y+'px;width:'+z.w+'px;height:'+z.h+'px';
      if(z.t==='stage'){ d.innerHTML='<i class="t"></i><i class="f"></i><i class="s"></i>'; }
      fl.appendChild(d); var p=el('div','es-pin'); var i=el('i','',++n); p.appendChild(i); p.appendChild(el('span','',z.label)); $('es-pins').appendChild(p); pins.push([d,p]);
    });
    [].forEach.call(document.querySelectorAll('#es-cam [data-c]'),function(b){ b.setAttribute('aria-pressed',b.dataset.c==='ens'); });
    cx=57; cz=-36; zs=innerWidth<900?.62:1; applyCam(); setTimeout(trackPins,850);
  }
  function trackPins(){ cancelAnimationFrame(raf); var t0=performance.now(); (function f(t){ place(); if(t-t0<900) raf=requestAnimationFrame(f); })(t0); }
  function place(){
    var sc=$('es-scene').getBoundingClientRect(); if(!sc.width) return;
    pins.forEach(function(q){ var r=q[0].getBoundingClientRect(), p=q[1];
      p.style.left=Math.min(sc.width-80,Math.max(80,r.left+r.width/2-sc.left))+'px'; p.style.top=Math.max(30,r.top-sc.top+r.height*.35)+'px'; });
  }
  $('es-cam').addEventListener('click',function(e){ var b=e.target.closest('[data-c]'); if(!b) return; [].forEach.call($('es-cam').children,function(x){x.setAttribute('aria-pressed',x===b);}); var c=CAM[b.dataset.c]; setCam(c[0],c[1],c[2]*small()); });
  var sc=$('es-scene'), dx=0, dn=false;
  sc.addEventListener('pointerdown',function(e){ dn=true; dx=e.clientX; sc.classList.add('drag'); try{sc.setPointerCapture(e.pointerId);}catch(_){} });
  sc.addEventListener('pointermove',function(e){ if(!dn) return; cz+=(e.clientX-dx)*.4; dx=e.clientX; applyCam(); });
  var end=function(){ dn=false; sc.classList.remove('drag'); }; sc.addEventListener('pointerup',end); sc.addEventListener('pointercancel',end);
  sc.addEventListener('wheel',function(e){ e.preventDefault(); zs=Math.min(1.5,Math.max(.6,zs-e.deltaY*.001)); applyCam(); },{passive:false});
  addEventListener('resize',function(){ if(!box.hidden) place(); });
})();
