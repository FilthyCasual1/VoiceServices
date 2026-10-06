import unittest
import test_app
from addon_sources.downloads import DownloadLibrary
class DownloadCategoriesTests(unittest.TestCase):
 setUp=test_app.PortalTests.setUp
 tearDown=test_app.PortalTests.tearDown
 def set_library(self):return DownloadLibrary(self.app.store,self.app.config,self.app.modules,'downloads')
 def test_category_assignment_search_and_delete_preserve_download(self):
  library=self.set_library();library.save_category({'name':'Network tools'});category=library.categories()[0]['id']
  library.add_link({'title':'Packet viewer','url':'https://internal.example/tool','category':str(category),'platform':'Windows','description':'Inspect traffic'})
  self.assertIn('Packet viewer',library.render(str(category),'traffic'));self.assertNotIn('Packet viewer',library.render('', 'missing'))
  library.save_category({'name':'Diagnostics','category':str(category)})
  self.assertIn('Diagnostics',library.render());library.remove_category(str(category))
  self.assertEqual(len(library.catalog()),1);self.assertIsNone(library.entries()[0]['category']);self.assertIn('Packet viewer',library.render('uncategorized'))
 def test_file_metadata_and_legacy_records_survive_reload(self):
  library=self.set_library()
  with self.app.store.connect() as db:
   db.execute("INSERT INTO downloads_files VALUES('tool.exe',1024,'abc')")
   db.execute("INSERT INTO downloads_catalog(title,version,platform,url) VALUES('Old link','1','Linux','https://internal.example/old')")
  self.assertEqual(len(library.entries()),2)
  library.save_details({'kind':'file','item':'tool.exe','title':'Internal tool','description':'Setup assistant','platform':'Windows'})
  reloaded=self.set_library();self.assertIn('Internal tool',reloaded.render());self.assertIn('Old link',reloaded.render())
 def test_validation_and_html_escaping(self):
  library=self.set_library();library.save_category({'name':'Utilities'})
  with self.assertRaises(ValueError):library.save_category({'name':'utilities'})
  with self.assertRaises(ValueError):library.add_link({'title':'Bad','url':'https://internal.example/tool','category':'9999'})
  with self.assertRaises(ValueError):library.save_details({'kind':'file','item':'missing','title':'Invalid'})
  library.add_link({'title':'<script>alert(1)</script>','url':'https://internal.example/tool','description':'<b>unsafe</b>'})
  self.assertNotIn('<script>',library.render());self.assertIn('&lt;script&gt;',library.render())
 def test_admin_routes_and_guest_filter(self):
  token,user=test_app.PortalTests.user(self,'admin')
  request=lambda *args,**kwargs:test_app.PortalTests.request(self,*args,**kwargs)
  response=request('/admin/downloads','POST',{'csrf':user['csrf'],'action':'save-category','name':'Utilities'},token)
  self.assertEqual(response['status'],'200 OK')
  category=self.app.downloads.categories()[0]['id']
  self.app.downloads.add_link({'title':'Network helper','url':'https://internal.example/helper','category':str(category)})
  self.assertIn('Network helper',request('/downloads',query='category='+str(category))['body'])
  self.assertNotIn('Network helper',request('/downloads',query='q=missing')['body'])
  self.assertNotEqual(request('/admin/downloads','POST',{'action':'remove-category','category':str(category)},token)['status'],'200 OK')
  self.assertEqual(len(self.app.downloads.categories()),1)
 def test_file_delete_confirmation_disk_failure_and_sizes(self):
  from unittest.mock import patch
  library=self.set_library();library.root.mkdir(exist_ok=True);(library.root/'tool.exe').write_bytes(b'tool')
  with self.app.store.connect() as db:db.execute("INSERT INTO downloads_files VALUES('tool.exe',4,'abc')")
  library.save_details({'kind':'file','item':'tool.exe','title':'Test tool'})
  self.assertIn('4 B',library.render());self.assertEqual(library.size(1536),'1.5 KB')
  with self.assertRaises(ValueError):library.remove_file({'item':'tool.exe'})
  with patch.object(library,'require_volume',side_effect=ValueError('Disk unavailable')):
   with self.assertRaises(ValueError):library.remove_file({'item':'tool.exe','confirm':'yes'})
  self.assertTrue((library.root/'tool.exe').exists())
  with patch.object(library,'require_volume'):library.remove_file({'item':'tool.exe','confirm':'yes'})
  self.assertFalse((library.root/'tool.exe').exists());self.assertEqual(library.entries(),[])
