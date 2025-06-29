import streamlit as st
import pikepdf
import io
import math
from PIL import Image

# --- Page Configuration ---
st.set_page_config(
    page_title="PDF Compressor Pro",
    page_icon="📄",
    layout="centered",
    initial_sidebar_state="auto",
)

# --- App State Management ---
# Using session state to hold data across reruns
def initialize_state():
    if 'compressed_pdf' not in st.session_state:
        st.session_state.compressed_pdf = None
    if 'original_filename' not in st.session_state:
        st.session_state.original_filename = None
    if 'compression_stats' not in st.session_state:
        st.session_state.compression_stats = {}

# Function to reset the state when a new file is uploaded
def reset_state():
    st.session_state.compressed_pdf = None
    st.session_state.original_filename = None
    st.session_state.compression_stats = {}

# --- UI Rendering ---
def main():
    """Main function to render the Streamlit app UI."""
    initialize_state()

    st.title("📄 PDF Compressor Pro")
    st.subheader("Reduce PDF file size by optimizing images within the document.")

    # File uploader
    uploaded_file = st.file_uploader(
        "Choose a PDF file to compress",
        type="pdf",
        on_change=reset_state  # Reset state when a new file is chosen
    )

    if uploaded_file is not None:
        st.sidebar.header("Compression Settings")

        # Simplified modes with clearer explanations
        mode_settings = {
            "Balanced": {"quality": 80, "info": "Good balance between size and quality."},
            "Aggressive": {"quality": 65, "info": "Noticeable quality loss, smaller size."},
            "Extreme": {"quality": 50, "info": "Significant quality loss, smallest size. Also removes metadata."},
        }

        compression_mode = st.sidebar.radio(
            "Select a compression mode:",
            options=list(mode_settings.keys()),
            index=0,
            help="This sets a baseline for image quality."
        )
        
        st.sidebar.info(mode_settings[compression_mode]["info"])
        
        # More intuitive image quality slider
        image_quality = st.sidebar.slider(
            "Fine-tune Image Quality (%)",
            min_value=10,
            max_value=95,
            value=mode_settings[compression_mode]["quality"],
            step=5,
            help="The quality of JPEG images after compression. Lower values mean smaller file size."
        )

        # Button to start the compression
        if st.button(f"Compress PDF ({compression_mode})"):
            st.session_state.original_filename = uploaded_file.name
            with st.spinner("Optimizing images and compressing PDF..."):
                compress_pdf(uploaded_file, compression_mode, image_quality)

    # --- Display Results ---
    if st.session_state.get('compression_stats'):
        stats = st.session_state.compression_stats
        
        st.header("Compression Results")
        
        # Priority 1: Check for and display any errors
        if stats.get('error'):
            st.error(stats['error'])
        
        # Priority 2: Check for and display info messages (e.g., already optimized)
        elif stats.get('info'):
            st.info(stats['info'])
        
        # If no error and no info, then it must be a successful compression
        else:
            # This block now only runs on success, so all keys should exist.
            col1, col2, col3 = st.columns(3)
            col1.metric("Original Size", stats.get('original_size_str', 'N/A'))
            col2.metric("Compressed Size", stats.get('compressed_size_str', 'N/A'))
            col3.metric("Space Saved", f"{stats.get('savings_str', 'N/A')} ({stats.get('reduction_ratio', 0.0):.1f}%)")

            if st.session_state.compressed_pdf:
                original_name = st.session_state.original_filename.replace('.pdf', '')
                st.download_button(
                    label="📥 Download Compressed PDF",
                    data=st.session_state.compressed_pdf,
                    file_name=f"{original_name}_compressed.pdf",
                    mime="application/pdf",
                )

# --- Helper & Core Logic Functions ---
def format_bytes(byte_count):
    """Formats bytes into a human-readable string (KB, MB, GB)."""
    if not isinstance(byte_count, (int, float)) or byte_count <= 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB")
    i = int(math.floor(math.log(byte_count, 1024)))
    p = math.pow(1024, i)
    s = round(byte_count / p, 2)
    return f"{s} {size_name[i]}"

def compress_pdf(file_obj, mode, quality):
    """
    Core function to compress a PDF using pikepdf and Pillow.
    
    Args:
        file_obj (BytesIO): The uploaded PDF file object.
        mode (str): The selected compression mode.
        quality (int): The target JPEG quality for images (1-95).
    """
    try:
        original_size = file_obj.getbuffer().nbytes
        pdf = pikepdf.Pdf.open(file_obj)
        
        num_images_processed = 0

        # Iterate through pages and images
        for i, page in enumerate(pdf.pages):
            for name in list(page.images.keys()):
                try:
                    img_obj = page.images[name]
                    # Attempt to convert to a PIL Image more robustly
                    pil_image = Image.open(io.BytesIO(img_obj.obj.read_bytes()))

                    # Convert RGBA or Palette modes to RGB as JPEG doesn't support alpha
                    if pil_image.mode in ('RGBA', 'P'):
                        pil_image = pil_image.convert('RGB')

                    # Re-compress image to JPEG format in memory
                    buffer = io.BytesIO()
                    pil_image.save(buffer, format="jpeg", quality=quality, optimize=True)
                    
                    # Replace the old image with the new compressed one
                    new_image_obj = pikepdf.Image(pdf, buffer)
                    page.images[name] = new_image_obj
                    num_images_processed += 1

                except Exception as e:
                    # Skip images that cause errors (e.g., unsupported formats, masks)
                    st.warning(f"Skipped an image on page {i+1} that could not be processed. Info: {e}")
                    continue

        # --- Mode-specific optimizations ---
        save_options = {
            "compress_streams": True,
            "linearize": True,
        }
        
        if mode == 'Extreme':
            try:
                del pdf.docinfo # Remove metadata
            except KeyError:
                pass

        buffer = io.BytesIO()
        pdf.save(buffer, **save_options)
        pdf.close()
        
        compressed_size = buffer.getbuffer().nbytes

        if compressed_size >= original_size:
            st.session_state.compression_stats = {
                'original_size_str': format_bytes(original_size),
                'info': f"This PDF seems to be highly optimized. New size ({format_bytes(compressed_size)}) is not smaller. Processed {num_images_processed} image(s)."
            }
            st.session_state.compressed_pdf = None
        else:
            st.session_state.compressed_pdf = buffer.getvalue()
            st.session_state.compression_stats = {
                'original_size_str': format_bytes(original_size),
                'compressed_size_str': format_bytes(compressed_size),
                'savings_str': format_bytes(original_size - compressed_size),
                'reduction_ratio': ((original_size - compressed_size) / original_size) * 100
            }
            
    except Exception as e:
        st.session_state.compression_stats = {
            'error': f"An error occurred: {e}. The PDF might be encrypted, corrupted, or have an unsupported format."
        }
        st.session_state.compressed_pdf = None
        print(f"Error compressing PDF: {e}")

if __name__ == "__main__":
    main()
