
function updateCourseTableCounts(settings) {
    const allRowsEnabled = settings.rowsT1 && settings.rowsT2 &&
        settings.otherTermRows && settings.missingCourseRows;
    document.querySelectorAll('details.course-details').forEach(details => {
        const summary = details.querySelector(':scope > summary');
        if (!summary) return;
        if (!summary.dataset.fullLabel) summary.dataset.fullLabel = summary.textContent;
        const fullLabel = summary.dataset.fullLabel;
        const count = fullLabel.match(/^Show\s+(\d+)/);
        if (!count) return;
        if (allRowsEnabled) {
            summary.textContent = fullLabel;
            return;
        }
        const rows = details.querySelectorAll(':scope > table > tbody > tr');
        const visible = Array.from(rows).filter(row =>
            (row.classList.contains('nf') || row.querySelector(':scope > td.col-code')) &&
            getComputedStyle(row).display !== 'none'
        ).length;
        summary.textContent = fullLabel.replace(/^Show\s+\d+/, 'Show ' + visible + ' / ' + count[1]);
    });
}
(function(){
  var sidebar = document.querySelector('.sidebar');
  if(!sidebar) return;
  var timer;
  sidebar.addEventListener('scroll', function(){
    clearTimeout(timer);
    timer = setTimeout(function(){ localStorage.setItem('sidebarScroll', sidebar.scrollTop); }, 100);
  });
  var groups = document.querySelectorAll('.fac-group');
  for(var i=0; i<groups.length; i++){
    groups[i].addEventListener('toggle', function(){
      var closed=[];
      var all=document.querySelectorAll('.fac-group');
      for(var j=0; j<all.length; j++){
        if(!all[j].open) closed.push(all[j].getAttribute('data-fac'));
      }
      localStorage.setItem('sidebarCollapsed', JSON.stringify(closed));
    });
  }
  var savedSettings;
  try { savedSettings = JSON.parse(localStorage.getItem('minorTableSettings') || '{}'); }
  catch (e) { savedSettings = {}; }
  if (savedSettings.prerequisites === undefined) {
    savedSettings.prerequisites = localStorage.getItem('hidePrereq') !== 'true';
  }
  var defaults = {term1:true, term2:true, otherTermColumn:false, prerequisites:true, schedule:false, schedule2:true, minors:false,
    rowsT1:true, rowsT2:true, otherTermRows:true, missingCourseRows:true, scroll:true};
  Object.keys(defaults).forEach(function(key){
    var checkbox = document.querySelector('[data-table-setting="' + key + '"]');
    if (!checkbox) return;
    checkbox.checked = savedSettings[key] === undefined ? defaults[key] : !!savedSettings[key];
    checkbox.addEventListener('change', applyTableSettings);
  });
  applyTableSettings();
})();

function applyTableSettings() {
  var classes = {
    term1:'hide-term-1', term2:'hide-term-2', otherTermColumn:'hide-term-3', prerequisites:'prereq-hidden',
    schedule:'hide-t1-schedule', schedule2:'hide-t2-schedule', minors:'hide-minors',
    rowsT1:'hide-rows-t1', rowsT2:'hide-rows-t2', otherTermRows:'hide-rows-t3',
    missingCourseRows:'hide-missing-course-rows',
    scroll:'table-scroll-disabled'
  };
  var settings = {};
  Object.keys(classes).forEach(function(key){
    var checkbox = document.querySelector('[data-table-setting="' + key + '"]');
    var shown = checkbox ? checkbox.checked : true;
    settings[key] = shown;
    document.body.classList.toggle(classes[key], !shown);
  });
  document.body.classList.add('filter-course-rows');
  var visibleColumns = 2 + ['term1','term2','otherTermColumn','prerequisites','schedule','schedule2','minors'].filter(function(key){
    return settings[key];
  }).length;
  document.querySelectorAll('tr.nf td[colspan]').forEach(function(cell){
    cell.colSpan = visibleColumns - 1;
  });
  updateCourseTableCounts(settings);
  localStorage.setItem('minorTableSettings', JSON.stringify(settings));
}

function setSettingsOpen(open) {
  var panel = document.querySelector('.settings-panel');
  var overlay = document.querySelector('.settings-overlay');
  var button = document.querySelector('.settings-toggle');
  if (!panel || !overlay) return;
  if (open) closeSidebar();
  panel.classList.toggle('open', open);
  overlay.classList.toggle('open', open);
  document.body.classList.toggle('settings-open', open);
  panel.setAttribute('aria-hidden', String(!open));
  if (button) button.setAttribute('aria-expanded', String(open));
}

function toggleSettings() {
  var panel = document.querySelector('.settings-panel');
  if (panel) setSettingsOpen(!panel.classList.contains('open'));
}

function closeSettings() { setSettingsOpen(false); }

// Prevent sidebar from navigating when clicking the already-active minor
document.querySelectorAll('.sidebar a').forEach(function(link) {
  link.addEventListener('click', function(e) {
    if (this.classList.contains('active')) {
      e.preventDefault();
    }
  });
});

function toggleSidebar() {
  var sidebar = document.querySelector('.sidebar');
  setSidebarOpen(!sidebar.classList.contains('open'));
}

function closeSidebar() {
  setSidebarOpen(false);
}

function setSidebarOpen(open) {
  var sidebar = document.querySelector('.sidebar');
  var overlay = document.querySelector('.sidebar-overlay');
  if (!sidebar || !overlay) return;
  if (open) closeSettings();
  sidebar.classList.toggle('open', open);
  overlay.classList.toggle('open', open);
  document.body.classList.toggle('sidebar-open', open);
  sidebar.setAttribute('aria-hidden', String(!open));
  document.querySelectorAll('.sidebar-toggle').forEach(function(button) {
    button.setAttribute('aria-expanded', String(open));
  });
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') { closeSidebar(); closeSettings(); }
});
