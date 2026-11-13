
function setSidebarVisibility(open){
 var sidebar=document.querySelector('.sidebar'),overlay=document.querySelector('.sidebar-overlay'),button=document.querySelector('.sidebar-toggle');
 if(!sidebar||!overlay)return;
 if(open)setSettingsVisibility(false);
 sidebar.classList.toggle('open',open);overlay.classList.toggle('open',open);document.body.classList.toggle('sidebar-visible',open);
 sidebar.setAttribute('aria-hidden',String(!open));if(button)button.setAttribute('aria-expanded',String(open));
}
function toggleSidebar(){var sidebar=document.querySelector('.sidebar');if(sidebar)setSidebarVisibility(!sidebar.classList.contains('open'))}
function setSettingsVisibility(open){
 var panel=document.querySelector('.settings-panel'),overlay=document.querySelector('.settings-overlay'),button=document.querySelector('.settings-toggle');
 if(!panel||!overlay)return;
 if(open)setSidebarVisibility(false);
 panel.classList.toggle('open',open);overlay.classList.toggle('open',open);document.body.classList.toggle('settings-open',open);
 panel.setAttribute('aria-hidden',String(!open));if(button)button.setAttribute('aria-expanded',String(open));
}
function toggleSettings(){var panel=document.querySelector('.settings-panel');if(panel)setSettingsVisibility(!panel.classList.contains('open'))}
function showRequirementScheme(identifier,updateUrl){
 var panels=document.querySelectorAll('[data-requirement-scheme]'),select=document.getElementById('requirementSchemeSelect'),matched=false;
 panels.forEach(function(panel){var active=panel.getAttribute('data-requirement-scheme')===identifier;panel.hidden=!active;if(active)matched=true});
 if(!matched&&panels.length){identifier=panels[0].getAttribute('data-requirement-scheme');panels.forEach(function(panel){panel.hidden=panel.getAttribute('data-requirement-scheme')!==identifier})}
 if(select)select.value=identifier;
 if(select){
  var option=select.options[select.selectedIndex],title=document.getElementById('activeRequirementSchemeTitle'),units=document.getElementById('activeRequirementSchemeUnits');
  if(title&&option)title.textContent=' — '+option.textContent;
  if(units&&option){var value=option.getAttribute('data-units')||'';units.textContent=value?value+' units':'';units.hidden=!value}
 }
 if(updateUrl!==false&&window.history&&window.URL){var url=new URL(window.location.href);url.searchParams.set('scheme',identifier);window.history.replaceState(null,'',url)}
}
function applyTableSettings(){
 var classes={term1:'hide-term-1',term2:'hide-term-2',prerequisites:'hide-enrolment',schedule:'hide-t1-schedule',schedule2:'hide-t2-schedule',minors:'hide-minors',unavailable:'hide-unavailable',scroll:'table-scroll-disabled'};
 var settings={};
 Object.keys(classes).forEach(function(key){
  var checkbox=document.querySelector('[data-table-setting="'+key+'"]'),shown=checkbox?checkbox.checked:true;
 settings[key]=shown;document.body.classList.toggle(classes[key],!shown);
 });
 var visibleColumns=2+['term1','term2','prerequisites','schedule','schedule2','minors'].filter(function(key){return settings[key]}).length;
 document.querySelectorAll('.course-group-row td[colspan]').forEach(function(cell){cell.colSpan=visibleColumns});
 document.querySelectorAll('tr.nf td[colspan]').forEach(function(cell){cell.colSpan=Math.max(1,visibleColumns-1)});
 localStorage.setItem('majorTableSettings',JSON.stringify(settings));
}
(function(){
 var schemeSelect=document.getElementById('requirementSchemeSelect');
 if(schemeSelect){
  var requested=new URLSearchParams(window.location.search).get('scheme');
  var requestedOption=Array.from(schemeSelect.options).find(function(option){return option.value===requested});
  if(requestedOption&&requestedOption.value!==schemeSelect.value)window.location.replace(window.publicationLink(requestedOption.getAttribute('data-url')));
  schemeSelect.addEventListener('change',function(){
   window.location.assign(window.publicationLink(this.options[this.selectedIndex].getAttribute('data-url')));
  });
 }
 var sidebar=document.querySelector('.sidebar'); if(!sidebar)return;
 var saved=localStorage.getItem('majorSidebarScroll'); if(saved!==null)sidebar.scrollTop=+saved;
 sidebar.addEventListener('scroll',function(){localStorage.setItem('majorSidebarScroll',sidebar.scrollTop)});
 document.querySelectorAll('.sidebar a.active').forEach(function(a){a.addEventListener('click',function(e){e.preventDefault()})});
 document.addEventListener('keydown',function(e){if(e.key==='Escape'){setSidebarVisibility(false);setSettingsVisibility(false)}});
 var saved;try{saved=JSON.parse(localStorage.getItem('majorTableSettings')||'{}')}catch(e){saved={}};
 if(saved.prerequisites===undefined){var legacyPrereq=localStorage.getItem('majorPrerequisites');saved.prerequisites=legacyPrereq?legacyPrereq!=='hidden':!window.matchMedia('(max-width:768px)').matches}
 if(saved.unavailable===undefined){saved.unavailable=localStorage.getItem('majorUnavailable')!=='hidden'}
 var defaults={term1:true,term2:true,prerequisites:true,schedule:false,schedule2:true,minors:false,unavailable:true,scroll:true};
 Object.keys(defaults).forEach(function(key){var checkbox=document.querySelector('[data-table-setting="'+key+'"]');if(!checkbox)return;checkbox.checked=saved[key]===undefined?defaults[key]:!!saved[key];checkbox.addEventListener('change',applyTableSettings)});
 applyTableSettings();
})();
