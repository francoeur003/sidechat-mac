"""Windows local OCR; no screenshots are written to disk or uploaded."""
import asyncio
import io

class OcrUnavailable(RuntimeError):
    pass

async def recognize_png(data, language='zh-Hans'):
    from winsdk.windows.storage.streams import InMemoryRandomAccessStream, DataWriter
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.globalization import Language
    engine = OcrEngine.try_create_from_language(Language(language))
    if engine is None:
        raise OcrUnavailable('请在 Windows 设置中安装简体中文语言包的文字识别功能，然后重启侧语。')
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream.get_output_stream_at(0))
    try:
        writer.write_bytes(data)
        await writer.store_async()
        await writer.flush_async()
        stream.seek(0)
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        try:
            if bitmap.pixel_width > OcrEngine.max_image_dimension or bitmap.pixel_height > OcrEngine.max_image_dimension:
                raise OcrUnavailable('框选区域过大，请只框选对方最新一条文字消息。')
            result = await engine.recognize_async(bitmap)
            return '\n'.join(line.text for line in result.lines).strip()
        finally:
            bitmap.close()
    finally:
        writer.close()
        stream.close()

def recognize_image(image):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return asyncio.run(recognize_png(buffer.getvalue()))
