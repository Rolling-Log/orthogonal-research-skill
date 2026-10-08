"""Exercise the public parser, metrics, PDF and HTML with 1-4 images."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT/'orthogonal-research-skill'
sys.path.insert(0,str(SKILL/'scripts'))
import build_report as br

class RepresentativeImagesTest(unittest.TestCase):
    def test_valid_row_renders_and_counts_each_label(self):
        br.register_fonts()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            image=root/'fixture.jpg'
            image.write_bytes((SKILL/'assets/sample/jpeg_fixture.jpg').read_bytes())
            for count in range(1,5):
                labels=['实物甲','实物乙','实物丙','实物丁'][:count]
                markdown='::: representative-images\n'+'\n'.join('![{}](fixture.jpg)'.format(x) for x in labels)+'\n:::'
                blocks=br.parse_markdown(markdown)
                self.assertEqual(br._reading_metrics(blocks,{},root,{}, {})['word_count'],3*count)
                html=br._html_blocks(blocks,{}, {})
                self.assertEqual(html.count('<figure>'),count)
                row=br.RepresentativeImages(blocks[0].rows,root)
                width,height=row.wrap(460,700)
                self.assertEqual(width,460)
                self.assertGreater(height,0)
                for item in row.images:
                    self.assertAlmostEqual(item.width/item.height,item.pixel_width/item.pixel_height)
                from reportlab.platypus import SimpleDocTemplate
                output=root/('row-'+str(count)+'.pdf')
                SimpleDocTemplate(str(output)).build([row])
                self.assertTrue(output.read_bytes().startswith(b'%PDF-'))

    def test_invalid_rows_fail_instead_of_silently_losing_images(self):
        cases=['', '\n'.join('![图](x.jpg)' for _ in range(5)),
               '![这是超过十个字的图片辅助文字](x.jpg)', 'not an image',
               '![](x.jpg)', '![{{@S001}}](x.jpg)', '![图](x.svg)']
        for content in cases:
            with self.subTest(content=content):
                with self.assertRaises(br.BuildError):
                    br.parse_markdown('::: representative-images\n'+content+'\n:::')
        with self.assertRaises(br.BuildError):
            br.parse_markdown('::: representative-images\n![图](x.jpg)')

    def test_paths_are_checked_for_html_and_pdf_reading_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            for path in ('../outside.jpg','https://example.com/image.jpg','missing.jpg'):
                with self.subTest(path=path):
                    blocks=br.parse_markdown('::: representative-images\n![图]('+path+')\n:::')
                    with self.assertRaises(br.BuildError):
                        br._reading_metrics(blocks,{},Path(directory),{}, {})

if __name__=='__main__':
    unittest.main()
