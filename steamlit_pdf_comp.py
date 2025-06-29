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
def initialize_state():
    """Initializes session state variables to persist data across reruns."""
    if 'compressed_pdf' not in st.session_state:
        st.session_state.compressed_pdf = None
    if 'original_filename' not in st.session_state:
        st.session_state.original_filename = None
    if 'compression_stats' not in st.session_state:
        st.session_state.compression_stats = {}

def reset_state():
    """Resets the session state when a new file is uploaded or action is taken."""
    st.session_state.compressed_pdf = None
    st.session_state.original_filename = None
    st.session_state.compression_stats = {}

# --- UI Rendering ---
def main():
    """Main function to render the Streamlit app UI."""
    initialize_state()

    st.title("📄 PDF Compressor Pro")
    st.subheader("Reduce PDF file size by downsampling and re-compressing images.")

    uploaded_file = st.file_uploader(
        "Choose a PDF file to compress",
        type="pdf",
        on_change=reset_state
    )

    if uploaded_file is not None:
        st.sidebar.header("Compression Settings")

        mode_settings = {
            "Balanced": {"ppi": 150, "quality": 75, "info": "Good balance between size and quality (150 PPI)."},
            "Aggressive": {"ppi": 96, "quality": 65, "info": "Smaller size, good for screen viewing (96 PPI)."},
            "Extreme": {"ppi": 72, "quality": 50, "info": "Smallest size, noticeable quality loss (72 PPI). Also removes metadata."},
        }

        compression_mode = st.sidebar.radio(
            "Select a compression mode:",
            options=list(mode_settings.keys()),
            index=0,
            help="This sets a baseline for image resolution and quality."
        )
        
        st.sidebar.info(mode_settings[compression_mode]["info"])
        
        target_ppi = st.sidebar.slider(
            "Image Resolution (PPI)",
            min_value=50,
            max_value=300,
            value=mode_settings[compression_mode]["ppi"],
            step=10,
            help="Pixels Per Inch. Images with a higher resolution will be downsampled to this value."
        )

        image_quality = st.sidebar.slider(
            "Image Quality (%)",
            min_value=10,
            max_value=95,
            value=mode_settings[compression_mode]["quality"],
            step=5,
            help="The quality of JPEG images after compression. Lower values mean smaller file size."
        )

        if st.button(f"Compress PDF ({compression_mode})"):
            st.session_state.original_filename = uploaded_file.name
            with st.spinner("Downsampling images and compressing PDF..."):
                compress_pdf(uploaded_file, compression_mode, target_ppi, image_quality)

    # --- Display Results ---
    if st.session_state.get('compression_stats'):
        stats = st.session_state.compression_stats
        
        st.header("Compression Results")
        
        if stats.get('error'):
            st.error(stats['error'])
        elif stats.get('info'):
            st.info(stats['info'])
        else:
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

def compress_pdf(file_obj, mode, target_ppi, quality):
    """
    Core function to compress a PDF by downsampling and re-compressing images.
    
    Args:
        file_obj (BytesIO): The uploaded PDF file object.
        mode (str): The selected compression mode.
        target_ppi (int): The target PPI for downsampling images.
        quality (int): The target JPEG quality for images (1-95).
    """
    try:
        original_size = file_obj.getbuffer().nbytes
        pdf = pikepdf.Pdf.open(file_obj)
        
        num_images_processed = 0
        num_images_skipped = 0

        for page in pdf.pages:
            for name in list(page.images.keys()):
                try:
                    img_obj = page.images[name]
                    pil_image = Image.open(io.BytesIO(img_obj.obj.read_bytes()))
                    
                    # Heuristic to decide if an image should be downsampled
                    # Longest side of an A4 page is ~11.7 inches.
                    # Max pixel dimension = target_ppi * page_dimension
                    max_pixels = target_ppi * 12 # Assume max page dimension of 12 inches
                    
                    if max(pil_image.width, pil_image.height) <= max_pixels:
                        # Image is already small enough, no need to downsample
                        continue

                    # Downsample the image
                    scale_ratio = max_pixels / max(pil_image.width, pil_image.height)
                    new_width = int(pil_image.width * scale_ratio)
                    new_height = int(pil_image.height * scale_ratio)
                    
                    resized_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

                    # Convert RGBA/P to RGB as JPEG doesn't support alpha
                    if resized_image.mode in ('RGBA', 'P'):
                        resized_image = resized_image.convert('RGB')

                    # Re-compress image to JPEG format in memory
                    buffer = io.BytesIO()
                    resized_image.save(buffer, format="jpeg", quality=quality, optimize=True)
                    
                    # Replace the old image with the new compressed one
                    page.images[name] = pikepdf.Image(pdf, buffer)
                    num_images_processed += 1

                except Exception as e:
                    num_images_skipped += 1
                    print(f"Skipping an image due to error: {e}")
                    continue
        
        if num_images_skipped > 0:
            st.warning(f"Skipped {num_images_skipped} image(s) that could not be processed (e.g., masks or unsupported formats).")

        # --- Mode-specific optimizations ---
        save_options = {"compress_streams": True, "linearize": True}
        if mode == 'Extreme':
            try:
                del pdf.docinfo
            except KeyError:
                pass

        buffer = io.BytesIO()
        pdf.save(buffer, **save_options)
        pdf.close()
        
        compressed_size = buffer.getbuffer().nbytes

        if compressed_size >= original_size:
            st.session_state.compression_stats = {
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
