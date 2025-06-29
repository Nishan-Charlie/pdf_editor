import streamlit as st
import pikepdf
import io
import math

# --- Page Configuration ---
st.set_page_config(
    page_title="PDF Compressor Pro",
    page_icon="📄",
    layout="centered",
    initial_sidebar_state="auto",
)

# --- App State Management ---
# Initialize session state variables to ensure they persist across reruns.
def initialize_state():
    if 'compressed_pdf' not in st.session_state:
        st.session_state.compressed_pdf = None
    if 'original_filename' not in st.session_state:
        st.session_state.original_filename = None
    if 'compression_stats' not in st.session_state:
        st.session_state.compression_stats = {}
    if 'processing' not in st.session_state:
        st.session_state.processing = False

# Function to reset the state, e.g., when a new file is uploaded
def reset_state():
    st.session_state.compressed_pdf = None
    st.session_state.original_filename = None
    st.session_state.compression_stats = {}
    st.session_state.processing = False

# --- UI Rendering ---
def main():
    """Main function to render the Streamlit app UI."""
    initialize_state()

    st.title("📄 PDF Compressor Pro")
    st.subheader("Reduce PDF file size efficiently without compromising too much on quality.")

    # File uploader
    uploaded_file = st.file_uploader(
        "Choose a PDF file",
        type="pdf",
        on_change=reset_state  # Reset when a new file is uploaded
    )

    if uploaded_file is not None:
        # Once a file is uploaded, show compression options
        st.sidebar.header("Compression Settings")

        # Define compression modes and their corresponding default PPI settings
        mode_settings = {
            "Balanced": {"ppi": 150, "info": "Good balance between size and quality (150 PPI)."},
            "Aggressive": {"ppi": 100, "info": "Smaller size, noticeable quality loss (100 PPI)."},
            "Extreme": {"ppi": 72, "info": "Lowest quality, smallest size (72 PPI). Also removes metadata."},
        }

        compression_mode = st.sidebar.radio(
            "Select a compression mode:",
            options=list(mode_settings.keys()),
            index=0, # Default to 'Balanced'
            help="Higher PPI means better quality but larger file size."
        )
        
        st.sidebar.info(mode_settings[compression_mode]["info"])
        
        # Allow fine-tuning of image quality (PPI)
        image_ppi = st.sidebar.slider(
            "Fine-tune Image Quality (PPI)",
            min_value=50,
            max_value=300,
            value=mode_settings[compression_mode]["ppi"],
            step=10,
            help="Pixels Per Inch. Lower values reduce image quality and file size."
        )

        # Button to trigger the compression process
        if st.button("Compress PDF"):
            st.session_state.processing = True
            st.session_state.original_filename = uploaded_file.name
            
            with st.spinner(f"Compressing with '{compression_mode}' mode..."):
                compress_pdf(uploaded_file, compression_mode, image_ppi)

    # --- Display Results ---
    # Show results only after processing is complete
    if st.session_state.get('compression_stats'):
        stats = st.session_state.compression_stats
        
        st.header("Compression Results")
        
        if stats.get('error'):
            st.error(stats['error'])
        else:
            col1, col2, col3 = st.columns(3)
            col1.metric("Original Size", stats['original_size_str'])
            col2.metric("Compressed Size", stats['compressed_size_str'])
            col3.metric("Space Saved", f"{stats['savings_str']} ({stats['reduction_ratio']:.1f}%)")

            # Provide the download button if compression was successful
            if st.session_state.compressed_pdf:
                original_name = st.session_state.original_filename.replace('.pdf', '')
                st.download_button(
                    label="📥 Download Compressed PDF",
                    data=st.session_state.compressed_pdf,
                    file_name=f"{original_name}_compressed.pdf",
                    mime="application/pdf",
                )
            elif stats.get('info'):
                st.info(stats['info'])


# --- Helper & Core Logic Functions ---
def format_bytes(byte_count):
    """Formats bytes into a human-readable string (KB, MB, GB)."""
    if byte_count == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB")
    i = int(math.floor(math.log(byte_count, 1024)))
    p = math.pow(1024, i)
    s = round(byte_count / p, 2)
    return f"{s} {size_name[i]}"

def compress_pdf(file_obj, mode, ppi):
    """
    Core function to perform PDF compression using pikepdf.
    
    Args:
        file_obj (BytesIO): The uploaded PDF file object.
        mode (str): The selected compression mode ('Balanced', 'Aggressive', 'Extreme').
        ppi (int): The target PPI for image downsampling.
    """
    try:
        original_size = file_obj.getbuffer().nbytes
        pdf = pikepdf.Pdf.open(file_obj)

        # --- Key Compression Step: Image Downsampling ---
        # This is the most effective way to reduce size in PDFs with images.
        for page in pdf.pages:
            for name, image in page.images.items():
                # Only attempt to re-encode if it's a raw image or can be improved
                raw_image = pikepdf.RawImage(image)
                if raw_image:
                    page.images[name] = pdf.make_image(
                        raw_image,
                        width=raw_image.width,
                        height=raw_image.height,
                        ppi=ppi
                    )

        # --- Mode-specific optimizations ---
        save_options = {
            "compress_streams": True,
            "linearize": True, # Optimizes for web viewing
            "deterministic_id": True # Helps with consistent output
        }
        
        if mode == 'Extreme':
            # Remove metadata for additional savings
            try:
                del pdf.docinfo
            except KeyError:
                pass # No docinfo to delete
            
            # This is an aggressive option that can break some PDFs, use with caution.
            # It removes things like form fields, annotations, etc.
            # pdf.flatten() 

        # Save the compressed PDF to a buffer in memory
        buffer = io.BytesIO()
        pdf.save(buffer, **save_options)
        pdf.close()
        
        compressed_size = buffer.getbuffer().nbytes

        # --- CRITICAL CHECK: Ensure file size was actually reduced ---
        if compressed_size >= original_size:
            st.session_state.compression_stats = {
                'original_size_str': format_bytes(original_size),
                'info': f"This PDF is already highly optimized. The compressed file ({format_bytes(compressed_size)}) is not smaller than the original."
            }
            st.session_state.compressed_pdf = None # No file to download
        else:
            # Successful compression
            st.session_state.compressed_pdf = buffer.getvalue()
            st.session_state.compression_stats = {
                'original_size_str': format_bytes(original_size),
                'compressed_size_str': format_bytes(compressed_size),
                'savings_str': format_bytes(original_size - compressed_size),
                'reduction_ratio': ((original_size - compressed_size) / original_size) * 100
            }
            
    except Exception as e:
        # Handle errors during processing
        st.session_state.compression_stats = {
            'error': f"An error occurred: {e}. The PDF might be corrupted or encrypted."
        }
        st.session_state.compressed_pdf = None
        print(f"Error compressing PDF: {e}")

if __name__ == "__main__":
    main()

