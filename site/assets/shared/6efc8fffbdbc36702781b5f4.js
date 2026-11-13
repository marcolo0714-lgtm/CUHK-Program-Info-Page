
(function(){var closed=JSON.parse(localStorage.getItem('sidebarCollapsed')||'[]');
var groups=document.querySelectorAll('.fac-group');
for(var i=0;i<groups.length;i++){if(closed.indexOf(groups[i].getAttribute('data-fac'))!==-1)groups[i].removeAttribute('open');}
var st=localStorage.getItem('sidebarScroll');
if(st!==null)document.querySelector('.sidebar').scrollTop=+st;})();
