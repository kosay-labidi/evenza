/* =====================================================================
   Évenza · accueil « 5 mondes » (three.js r128)
   De vraies photos d'événements placées dans l'espace 3D (avec relief),
   des effets 3D par-dessus (confettis, pétales, projecteurs, feux d'artifice…).
   La molette fait avancer la caméra d'un monde à l'autre, à travers un
   tunnel de lumière. La scène reste en fond pendant tout l'accueil.
   ===================================================================== */
(() => {
  const $ = s => document.querySelector(s);
  const MONDES = JSON.parse($('#mondes-data').textContent);
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const mobile = matchMedia('(max-width: 760px)').matches;
  const sections = [...document.querySelectorAll('.world-sec')];
  const dots = [...document.querySelectorAll('.rail a')];

  /* ---------- légendes : apparition quand la section arrive ---------- */
  const io = new IntersectionObserver(es => es.forEach(e => e.target.classList.toggle('in', e.isIntersecting)), { threshold: .25 });
  document.querySelectorAll('.world-card, .intro-in').forEach(el => io.observe(el));

  /* ---------- mode sans 3D : photos en fond de chaque section ---------- */
  let glOk = false; try { glOk = !!document.createElement('canvas').getContext('webgl'); } catch (e) { }
  if (!window.THREE || !glOk || reduce) {
    document.body.classList.add('static');
    sections.forEach((s, i) => s.style.backgroundImage = `linear-gradient(rgba(8,7,13,.45),rgba(8,7,13,.75)),url(${MONDES[i].img})`);
    $('#loader') && $('#loader').remove();
    document.querySelectorAll('.world-card, .intro-in').forEach(el => el.classList.add('in'));
    return;
  }

  /* ================= moteur ================= */
  const renderer = new THREE.WebGLRenderer({ canvas: $('#gl'), antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(devicePixelRatio, mobile ? 1.5 : 1.75));
  renderer.outputEncoding = THREE.sRGBEncoding;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x050409);
  scene.fog = new THREE.Fog(0x050409, 60, 150);
  const camera = new THREE.PerspectiveCamera(50, 1, .1, 400);

  const SP = 90;          // distance entre deux mondes
  const D = 32;           // distance caméra → photo à l'arrêt
  const N = MONDES.length;
  const rnd = (a, b) => a + Math.random() * (b - a);
  const dirAlea = () => { const u = rnd(-1, 1), a = rnd(0, Math.PI * 2), r = Math.sqrt(1 - u * u); return new THREE.Vector3(r * Math.cos(a), u, r * Math.sin(a)); };
  let composer = null, bloom = null, filmPass = null, ready = false;
  const sm = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
  const ease = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

  /* point lumineux réutilisable */
  const dotTex = (() => { const c = document.createElement('canvas'); c.width = c.height = 64; const g = c.getContext('2d'), r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(.25, 'rgba(255,255,255,.75)'); r.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = r; g.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c); })();

  /* ---------- chargement des photos ---------- */
  const manager = new THREE.LoadingManager();
  const ldBar = $('#ldbar');
  manager.onProgress = (u, l, t) => { if (ldBar) ldBar.style.width = (l / t * 100) + '%'; };
  manager.onLoad = () => { const L = $('#loader'); if (L) { L.style.opacity = 0; setTimeout(() => L.remove(), 900); } };
  const loader = new THREE.TextureLoader(manager);

  /* ---------- photo en relief (2.5D) : le bas de l'image avance vers la caméra ---------- */
  const photoVS = `
    uniform sampler2D map; uniform float uDepth; uniform float uTime; varying vec2 vUv; varying float vD;
    void main(){
      vUv = uv;
      vec3 c = texture2D(map, uv).rgb;
      float lum = dot(c, vec3(.299,.587,.114));
      float d = smoothstep(.0, 1., 1. - uv.y) * .75 + lum * .25;      // profondeur estimée
      d += .12 * (1. - smoothstep(.0, .6, distance(uv, vec2(.5,.35))));
      vD = d;
      vec3 p = position; p.z += d * uDepth + sin(uTime*.6 + uv.x*3.)*.04;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.);
    }`;
  const photoFS = `
    uniform sampler2D map; uniform float uOpacity; uniform vec3 uTint; uniform float uGlow; varying vec2 vUv; varying float vD;
    void main(){
      vec3 c = texture2D(map, vUv).rgb;
      c = mix(c, c * uTint, .35);
      c *= .74 + uGlow * .16;
      float e = smoothstep(.0, .06, vUv.x) * smoothstep(1., .94, vUv.x) * smoothstep(.0, .06, vUv.y) * smoothstep(1., .94, vUv.y);
      gl_FragColor = vec4(c, uOpacity * e);
    }`;

  const mondes = MONDES.map((m, i) => {
    const z = -i * SP;
    const tex = loader.load(m.img, t => { t.encoding = THREE.sRGBEncoding; t.anisotropy = renderer.capabilities.getMaxAnisotropy(); w.aspect = t.image.width / t.image.height; resize(); });
    const mat = new THREE.ShaderMaterial({
      uniforms: { map: { value: tex }, uOpacity: { value: 0 }, uDepth: { value: 4.5 }, uTime: { value: 0 }, uTint: { value: new THREE.Color(m.teinte) }, uGlow: { value: 0 } },
      vertexShader: photoVS, fragmentShader: photoFS, transparent: true, depthWrite: false
    });
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(1, 1, mobile ? 90 : 160, mobile ? 60 : 100), mat);
    plane.position.set(0, 0, z - D);
    scene.add(plane);
    // cadre lumineux : on voit le monde suivant comme un portail
    const frame = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.PlaneGeometry(1, 1)),
      new THREE.LineBasicMaterial({ color: new THREE.Color(m.accent), transparent: true, opacity: 0, toneMapped: false }));
    frame.position.copy(plane.position).add(new THREE.Vector3(0, 0, .2));
    scene.add(frame);
    const w = { ...m, i, z, plane, mat, frame, aspect: 1.5, fx: [] };
    return w;
  });

  /* ---------- effets 3D propres à chaque monde ---------- */
  const fxBox = w => ({ z0: w.z - D + 3, z1: w.z - 6 });

  // confettis / pétales : petits plans qui tombent en tournant
  function chute(w, { n, couleurs, taille, vitesse, balance, forme }) {
    const geo = forme === 'petale' ? new THREE.CircleGeometry(taille, 10) : new THREE.PlaneGeometry(taille * 2, taille);
    if (forme === 'petale') geo.scale(1, .55, 1);
    const mesh = new THREE.InstancedMesh(geo, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide, transparent: true, opacity: 0, toneMapped: false }), n);
    const { z0, z1 } = fxBox(w), col = new THREE.Color(), P = [];
    for (let k = 0; k < n; k++) { P.push({ x: rnd(-22, 22), y: rnd(-12, 14), z: rnd(z0, z1), r: rnd(0, 6), vr: rnd(-2, 2), s: rnd(.6, 1.3), ph: rnd(0, 6) }); mesh.setColorAt(k, col.set(couleurs[k % couleurs.length])); }
    scene.add(mesh);
    const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler(), v = new THREE.Vector3(), s = new THREE.Vector3();
    w.fx.push({ obj: mesh, update(t, dt, a) {
      mesh.material.opacity = a * .95;
      P.forEach((p, k) => { p.y -= vitesse * p.s * dt; if (p.y < -14) p.y = 14; p.r += p.vr * dt;
        e.set(p.r, p.r * .7, p.r * .3); q.setFromEuler(e); v.set(p.x + Math.sin(t * balance + p.ph) * 1.2, p.y, p.z); s.setScalar(p.s); m4.compose(v, q, s); mesh.setMatrixAt(k, m4); });
      mesh.instanceMatrix.needsUpdate = true; } });
  }
  // bokeh / poussière lumineuse
  function bokeh(w, { n, couleur, taille, derive }) {
    const { z0, z1 } = fxBox(w), arr = new Float32Array(n * 3), B = [];
    for (let k = 0; k < n; k++) B.push([rnd(-24, 24), rnd(-13, 14), rnd(z0, z1), rnd(0, 6)]);
    const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(arr, 3));
    const mat = new THREE.PointsMaterial({ size: taille, map: dotTex, color: couleur, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false });
    scene.add(new THREE.Points(geo, mat));
    w.fx.push({ update(t, dt, a) {
      mat.opacity = a * (.7 + Math.sin(t * 1.7) * .15);
      B.forEach((b, k) => { arr[k * 3] = b[0] + Math.sin(t * .3 + b[3]) * derive; arr[k * 3 + 1] = b[1] + Math.sin(t * .4 + b[3] * 1.3) * derive * .6; arr[k * 3 + 2] = b[2]; });
      geo.attributes.position.needsUpdate = true; } });
  }
  // faisceaux de projecteurs (cônes additifs qui balaient)
  function projecteurs(w, couleurs) {
    const mk = c => new THREE.ShaderMaterial({ uniforms: { color: { value: new THREE.Color(c) }, k: { value: 0 } }, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, toneMapped: false,
      vertexShader: 'varying float vD; varying vec3 vN; varying vec3 vV; void main(){ vD = clamp(-position.y/30.,0.,1.); vec4 mv = modelViewMatrix*vec4(position,1.); vN = normalize(normalMatrix*normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix*mv; }',
      fragmentShader: 'uniform vec3 color; uniform float k; varying float vD; varying vec3 vN; varying vec3 vV; void main(){ float a = pow(1.-vD,2.)*pow(abs(dot(vN,vV)),1.5)*.35*k; gl_FragColor = vec4(color*a*2., a); }' });
    const B = couleurs.map((c, k) => { const g = new THREE.ConeGeometry(3.4, 30, 32, 1, true); g.translate(0, -15, 0);
      const m = new THREE.Mesh(g, mk(c)); m.position.set(-16 + k * (32 / (couleurs.length - 1)), 16, w.z - D + 8); m.userData.ph = k * 1.3; scene.add(m); return m; });
    w.fx.push({ update(t, dt, a) { B.forEach(b => { b.rotation.z = Math.sin(t * .7 + b.userData.ph) * .5; b.rotation.x = .25 + Math.sin(t * .5 + b.userData.ph) * .15; b.material.uniforms.k.value = a * (.8 + Math.sin(t * 4 + b.userData.ph) * .2); }); } });
  }
  // feux d'artifice
  function artifices(w) {
    const n = 6, per = 140, arr = new Float32Array(n * per * 3), col = new Float32Array(n * per * 3), S = [];
    const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(arr, 3)); geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    const mat = new THREE.PointsMaterial({ size: .45, map: dotTex, vertexColors: true, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false });
    scene.add(new THREE.Points(geo, mat));
    const pal = ['#ff3d8b', '#ffb547', '#36e0ff', '#c6ff5e', '#ffffff', '#b28cff'].map(c => new THREE.Color(c));
    for (let b = 0; b < n; b++) S.push({ t0: -b * .7, x: 0, y: 0, z: 0, c: pal[0], dirs: [...Array(per)].map(() => dirAlea().multiplyScalar(rnd(4, 7))) });
    w.fx.push({ update(t, dt, a) {
      mat.opacity = a;
      S.forEach((s, b) => { let age = t - s.t0;
        if (age > 2.6 || age < 0) { s.t0 = t + rnd(0, .8); s.x = rnd(-18, 18); s.y = rnd(4, 12); s.z = w.z - D + rnd(6, 14); s.c = pal[(Math.random() * pal.length) | 0]; age = 0; }
        const k = 1 - Math.exp(-age * 2.4), fade = Math.max(0, 1 - age / 2.6);
        s.dirs.forEach((d, j) => { const o = (b * per + j) * 3; arr[o] = s.x + d.x * k; arr[o + 1] = s.y + d.y * k - age * age * .9; arr[o + 2] = s.z + d.z * k * .4;
          col[o] = s.c.r * fade; col[o + 1] = s.c.g * fade; col[o + 2] = s.c.b * fade; }); });
      geo.attributes.position.needsUpdate = true; geo.attributes.color.needsUpdate = true; } });
  }

  const FX = {
    concert: w => { projecteurs(w, ['#ff3d8b', '#36e0ff', '#ffb547', '#b28cff', '#ff3d8b']); chute(w, { n: mobile ? 160 : 320, couleurs: ['#ff3d8b', '#ffb547', '#36e0ff', '#ffffff', '#c6ff5e'], taille: .14, vitesse: 3, balance: 1.5 }); bokeh(w, { n: 120, couleur: 0xffc0e0, taille: .5, derive: 1 }); },
    mariage: w => { chute(w, { n: mobile ? 120 : 240, couleurs: ['#ffd6e0', '#ffffff', '#ffc2cf', '#fff0e0'], taille: .18, vitesse: 1.1, balance: .8, forme: 'petale' }); bokeh(w, { n: 160, couleur: 0xffd59a, taille: 1.1, derive: .6 }); },
    conference: w => { bokeh(w, { n: 260, couleur: 0x8fd8ff, taille: .22, derive: 1.6 }); bokeh(w, { n: 40, couleur: 0x36e0ff, taille: 1.2, derive: .5 }); },
    gala: w => { bokeh(w, { n: 200, couleur: 0xffd27a, taille: .35, derive: .8 }); bokeh(w, { n: 50, couleur: 0xfff0c8, taille: 1.4, derive: .4 }); chute(w, { n: 90, couleurs: ['#ffd27a', '#e8b860'], taille: .08, vitesse: .7, balance: .6 }); },
    festival: w => { artifices(w); chute(w, { n: mobile ? 140 : 260, couleurs: ['#c6ff5e', '#ff3d8b', '#ffb547', '#36e0ff'], taille: .14, vitesse: 2.4, balance: 1.2 }); bokeh(w, { n: 100, couleur: 0xffe0a0, taille: .6, derive: 1 }); }
  };
  mondes.forEach(w => (FX[w.cle] || FX.gala)(w));

  /* ---------- tunnel de lumière entre les mondes (s'étire avec la vitesse) ---------- */
  const SN = mobile ? 500 : 1100;
  const streaks = new THREE.InstancedMesh(new THREE.BoxGeometry(.035, .035, 1), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }), SN);
  const SS = [], sc = new THREE.Color();
  for (let k = 0; k < SN; k++) { const a = rnd(0, Math.PI * 2), r = rnd(5, 16); SS.push({ x: Math.cos(a) * r, y: Math.sin(a) * r, z: rnd(-(N - 1) * SP - 40, 40), l: rnd(.6, 1.6) });
    streaks.setColorAt(k, sc.set(['#ffb547', '#ff3d8b', '#36e0ff', '#ffffff'][k % 4])); }
  scene.add(streaks);

  /* ---------- post-traitement : halo + grain de film + vignette ---------- */
  if (THREE.EffectComposer && THREE.UnrealBloomPass && THREE.ShaderPass) {
    composer = new THREE.EffectComposer(renderer);
    composer.addPass(new THREE.RenderPass(scene, camera));
    bloom = new THREE.UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), .6, .55, .86);
    composer.addPass(bloom);
    filmPass = new THREE.ShaderPass({
      uniforms: { tDiffuse: { value: null }, uTime: { value: 0 }, uAb: { value: 0 } },
      vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }',
      fragmentShader: `uniform sampler2D tDiffuse; uniform float uTime; uniform float uAb; varying vec2 vUv;
        float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233))) * 43758.5453); }
        void main(){ vec2 d = (vUv - .5) * uAb;
          vec3 c = vec3(texture2D(tDiffuse, vUv + d).r, texture2D(tDiffuse, vUv).g, texture2D(tDiffuse, vUv - d).b);
          c += (h(vUv * 900. + uTime) - .5) * .045;
          c *= 1. - smoothstep(.45, 1.05, length(vUv - .5) * 1.25);
          gl_FragColor = vec4(c, 1.); }`
    });
    composer.addPass(filmPass);
  }

  function coverScale(w, dist) {     // la photo couvre tout l'écran à la distance d'arrêt
    const vh = 2 * dist * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)), vw = vh * camera.aspect;
    const s = Math.max(vw / w.aspect, vh) * 1.12;
    return [s * w.aspect, s];
  }
  function resize() {
    if (!ready) return;
    const W = innerWidth, H = innerHeight;
    renderer.setSize(W, H, false); camera.aspect = W / H; camera.fov = W < 760 ? 62 : 50; camera.updateProjectionMatrix();
    composer && composer.setSize(W, H);
    mondes.forEach(w => { const [sx, sy] = coverScale(w, D + 6); w.plane.scale.set(sx, sy, 1); w.frame.scale.set(sx, sy, 1); });
  }
  ready = true; addEventListener('resize', resize); resize();

  /* ---------- défilement → progression ---------- */
  const flow = $('#flow'), first = sections[0], last = sections[sections.length - 1];
  let target = 0, p = 0, pv = 0, mx = 0, my = 0, tmx = 0, tmy = 0;
  const read = () => {
    const start = flow.offsetTop, end = last.offsetTop + last.offsetHeight - innerHeight;
    target = Math.min(1, Math.max(0, (scrollY - start) / Math.max(1, end - start)));
    // pastille active
    const cur = Math.min(N - 1, Math.floor(Math.max(0, target * (N + 1) - 1 + .35)));
    dots.forEach((d, k) => d.classList.toggle('on', k === cur));
  };
  addEventListener('scroll', read, { passive: true }); addEventListener('resize', read); read();
  addEventListener('pointermove', e => { tmx = (e.clientX / innerWidth - .5); tmy = (e.clientY / innerHeight - .5); }, { passive: true });

  /* Position de la caméra : un segment d'intro (on s'approche du 1er portail), puis un segment par monde.
     Dans un monde : 70 % du temps on avance doucement dans la photo, 30 % on traverse le tunnel vers le suivant. */
  function cameraZ(P) {
    const seg = P * (N + 1);
    if (seg < 1) return { z: mondes[0].z + 70 - 64 * ease(seg), i: 0, f: 0, intro: 1 - seg };
    const i = Math.min(N - 1, Math.floor(seg - 1)), f = Math.min(1, seg - 1 - i), z = mondes[i].z;
    if (f < .7 || i === N - 1) return { z: z + 6 - 9 * ease(Math.min(1, f / .7)), i, f, intro: 0 };
    const g = (f - .7) / .3;
    return { z: THREE.MathUtils.lerp(z - 3, mondes[i + 1].z + 6, ease(g)), i, f, intro: 0, warp: Math.sin(g * Math.PI) };
  }

  /* ================= boucle ================= */
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), v3 = new THREE.Vector3(), s3 = new THREE.Vector3();
  let last_ = 0, run = true, prevZ = 0, vel = 0;
  document.addEventListener('visibilitychange', () => { run = !document.hidden; if (run) { last_ = performance.now(); requestAnimationFrame(loop); } });

  function loop(ms) {
    if (!run) return;
    const t = ms / 1000, dt = Math.min(.05, Math.max(.001, (ms - last_) / 1000 || 1 / 60)); last_ = ms;
    const k = 4.2; pv += (k * k * (target - p) - 2 * k * pv) * dt; p += pv * dt;     // ressort : suit le scroll sans à-coups
    mx += (tmx - mx) * .05; my += (tmy - my) * .05;

    const c = cameraZ(Math.min(1, Math.max(0, p)));
    const side = c.i % 2 ? -1 : 1;
    camera.position.set(Math.sin(c.f * Math.PI) * 1.6 * side + mx * 1.2, Math.sin(t * .5) * .12 - my * .8, c.z);
    camera.lookAt(mx * 2, -my * 1.2, c.z - 40);
    camera.rotation.z += (c.warp || 0) * Math.sin(t * 2) * .02 + Math.sin(c.f * Math.PI) * .012 * side;
    vel += (Math.abs(c.z - prevZ) / dt - vel) * .15; prevZ = c.z;

    mondes.forEach(w => {
      const dist = c.z - w.plane.position.z;                  // distance caméra → photo
      const visible = sm(150, 70, dist) * sm(5, 15, dist);    // apparaît au loin, disparaît quand on la traverse
      w.mat.uniforms.uOpacity.value = visible;
      w.mat.uniforms.uTime.value = t;
      w.mat.uniforms.uGlow.value = sm(60, 30, dist);
      w.frame.material.opacity = sm(140, 80, dist) * sm(30, 55, dist) * .9;
      const fxA = sm(70, 38, dist) * sm(4, 12, dist);         // effets visibles quand on est « dans » le monde
      w.fx.forEach(fx => fx.update(t, dt, fxA));
    });

    const warp = Math.min(1, vel / 60);
    streaks.material.opacity = Math.max(warp, c.warp || 0) * .9;
    const stretch = 1 + Math.min(vel * .25, 22);
    SS.forEach((s, j) => { v3.set(s.x, s.y, s.z); s3.set(1, 1, s.l * stretch); m4.compose(v3, q, s3); streaks.setMatrixAt(j, m4); });
    streaks.instanceMatrix.needsUpdate = true;

    if (bloom) bloom.strength = .55 + warp * .5;
    if (filmPass) { filmPass.uniforms.uTime.value = t; filmPass.uniforms.uAb.value = .002 + warp * .012; }
    composer ? composer.render() : renderer.render(scene, camera);
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
})();
