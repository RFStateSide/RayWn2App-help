// Copyright RF StateSide LLC; SPDX-License-Identifier: LGPL-3.0-only
const $=id=>document.getElementById(id);
const current=location.pathname.split('/').pop()||'index.html';
document.querySelectorAll('nav a').forEach(a=>{if(a.getAttribute('href')===current)a.setAttribute('aria-current','page')});
$('contents').onclick=()=>{$('contents').setAttribute('aria-expanded',document.body.classList.toggle('show-nav'))};
$('search').oninput=()=>{const words=$('search').value.toLowerCase().trim().split(/\s+/).filter(Boolean);$('results').replaceChildren();if(!words.length)return;const matches=window.helpSearch.filter(p=>words.every(w=>(p.title+' '+p.text).toLowerCase().includes(w)));const count=document.createElement('p');count.textContent=matches.length+' matching topics';$('results').append(count);matches.forEach(p=>{const a=document.createElement('a');a.href=p.url;a.textContent=p.title;$('results').append(a)})};
$('search').onkeydown=e=>{if(e.key==='Enter')$('results').querySelector('a')?.click();if(e.key==='Escape'){$('search').value='';$('search').oninput()}};
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();document.body.classList.add('show-nav');$('contents').setAttribute('aria-expanded','true');$('search').focus()}});
const dialog=$('image-dialog'),img=$('enlarged'),box=$('image-scroll');let zoom=1,fitted=true,opener;
function render(){if(!img.naturalWidth)return;if(fitted)zoom=Math.min((box.clientWidth-20)/img.naturalWidth,(box.clientHeight-20)/img.naturalHeight,8);zoom=Math.max(.1,Math.min(zoom,8));img.style.width=img.naturalWidth*zoom+'px';img.style.height='auto';$('percent').textContent=Math.round(zoom*100)+'%'}
document.querySelectorAll('main a[href^="images/"]').forEach(a=>a.onclick=e=>{if(!dialog.showModal)return;e.preventDefault();opener=a;fitted=true;img.alt=a.querySelector('img')?.alt||'Help illustration';img.onload=render;img.src=a.href;dialog.showModal();render();$('close').focus()});
$('in').onclick=()=>{fitted=false;zoom*=1.25;render()};$('out').onclick=()=>{fitted=false;zoom/=1.25;render()};$('actual').onclick=()=>{fitted=false;zoom=1;render()};$('fit').onclick=()=>{fitted=true;render()};$('close').onclick=()=>dialog.close();dialog.onclose=()=>opener?.focus();window.addEventListener('resize',()=>{if(dialog.open&&fitted)render()});
