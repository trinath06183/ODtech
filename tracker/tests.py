import io
from PIL import Image
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
User = get_user_model()
from .models import Order, Lot, Product, SupplierCostOption
from .utils import compress_image_to_target

class ImageCompressionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.order = Order.objects.create(
            order_number='ORD-0001',
            customer_name='Test Customer',
            customer_phone='1234567890',
            created_by=self.user
        )
        self.lot = Lot.objects.create(
            order=self.order,
            lot_name='Lot 1',
            created_by=self.user
        )

    def test_compress_large_image(self):
        # Create a large image in memory (e.g., 1000x1000 pixels)
        img_byte_arr = io.BytesIO()
        large_img = Image.new('RGB', (1000, 1000), color='blue')
        large_img.save(img_byte_arr, format='JPEG')
        img_byte_arr.seek(0)
        
        uploaded_file = SimpleUploadedFile(
            "large_image.jpg", 
            img_byte_arr.read(), 
            content_type="image/jpeg"
        )
        
        # Test direct utility function
        compressed_file = compress_image_to_target(uploaded_file)
        compressed_size = len(compressed_file.read())
        
        # Output sizes for debugging
        print(f"\n[Test] Original size: {uploaded_file.size} bytes")
        print(f"[Test] Compressed size: {compressed_size} bytes")
        
        # Verify size constraints: max 20 KB (20480 bytes) and ideally close to 15-20 KB
        self.assertTrue(compressed_size <= 20 * 1024, f"Compressed size ({compressed_size}) exceeds 20 KB")
        # Since it is a solid color image, it compresses very well, but let's make sure it's at least valid
        self.assertTrue(compressed_size > 0, "Compressed file is empty")

    def test_preserve_non_image_file(self):
        # Create a dummy text file
        text_content = b"This is a dummy text document that should not be compressed."
        uploaded_file = SimpleUploadedFile(
            "document.txt",
            text_content,
            content_type="text/plain"
        )
        
        # Run utility
        result = compress_image_to_target(uploaded_file)
        result.seek(0)
        result_content = result.read()
        
        self.assertEqual(result_content, text_content, "Text file content changed")

    def test_product_model_save_compresses_image(self):
        # Create a large image
        img_byte_arr = io.BytesIO()
        large_img = Image.new('RGB', (800, 800), color='green')
        large_img.save(img_byte_arr, format='JPEG')
        img_byte_arr.seek(0)
        
        uploaded_file = SimpleUploadedFile(
            "product_image.jpg", 
            img_byte_arr.read(), 
            content_type="image/jpeg"
        )
        
        product = Product.objects.create(
            order=self.order,
            lot=self.lot,
            sl_no=1,
            item_name="Compressed Product",
            quantity=1,
            photo_or_document=uploaded_file,
            created_by=self.user
        )
        
        # Fetch file size from disk
        product.photo_or_document.seek(0)
        saved_size = product.photo_or_document.size
        print(f"[Test] Model product saved image size: {saved_size} bytes")
        
        self.assertTrue(saved_size <= 20 * 1024, f"Product saved image size ({saved_size}) exceeds 20 KB")
        self.assertTrue(product.photo_or_document.name.endswith('.jpg'))

    def test_supplier_option_model_save_compresses_image(self):
        # Create a large image
        img_byte_arr = io.BytesIO()
        large_img = Image.new('RGB', (800, 800), color='red')
        large_img.save(img_byte_arr, format='JPEG')
        img_byte_arr.seek(0)
        
        uploaded_file = SimpleUploadedFile(
            "supplier_quote_img.png", 
            img_byte_arr.read(), 
            content_type="image/png"
        )
        
        product = Product.objects.create(
            order=self.order,
            lot=self.lot,
            sl_no=2,
            item_name="Supplier Product",
            quantity=1,
            created_by=self.user
        )
        
        supplier_option = SupplierCostOption.objects.create(
            product=product,
            supplier_name="Test Supplier",
            photo_or_document=uploaded_file,
            created_by=self.user
        )
        
        supplier_option.photo_or_document.seek(0)
        saved_size = supplier_option.photo_or_document.size
        print(f"[Test] Model supplier saved image size: {saved_size} bytes")
        
        self.assertTrue(saved_size <= 20 * 1024, f"Supplier option saved image size ({saved_size}) exceeds 20 KB")
        self.assertTrue(supplier_option.photo_or_document.name.endswith('.jpg'))
