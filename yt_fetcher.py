import yt_dlp

def fetch_youtube_formats(url):
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats_to_return = []
            
            # Look for Video+Audio (MP4) and Audio-Only (MP3/M4A)
            for f in info.get('formats', []):
                # Filter for common useful formats with direct URLs
                if f.get('url'):
                    # Video + Audio options (usually mp4)
                    if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4':
                        formats_to_return.append({
                            'ext': 'MP4',
                            'quality': f.get('format_note', 'HD'),
                            'url': f['url']
                        })
                    # Audio Only options
                    elif f.get('vcodec') == 'none' and f.get('acodec') != 'none':
                        formats_to_return.append({
                            'ext': 'MP3',
                            'quality': f.get('abr', 128),
                            'url': f['url']
                        })

            # Sort and pick the best 5 options to avoid overwhelming the user
            return True, formats_to_return[-5:] 
    except Exception as e:
        return False, str(e)
