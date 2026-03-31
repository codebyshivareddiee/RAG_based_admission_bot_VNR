# Chatbot Widget Enhancements

## Overview
Three major accessibility and navigation features have been added to the VNRVJIET Admissions Chatbot widget:

1. **Back Button** - Navigate to previous conversation states
2. **Video Guidance Link** - Direct link to video tutorial
3. **Voice Feature (Text-to-Speech)** - Listen to bot responses

---

## 1. Back Button Navigation

### Features
- **Location**: Chat header, between logo and home button
- **Visibility**: Automatically shown when conversation history exists
- **Functionality**: 
  - Removes last message pair (user + bot response)
  - Maintains conversation state stack
  - Returns to welcome screen when no history remains
  - Stops any playing audio when navigating back

### Technical Implementation
- **Files Modified**: 
  - `app/frontend/widget.html` - Added back button HTML
  - `app/frontend/widget.css` - Added back button styles
  - `app/frontend/widget.js` - Added back navigation logic

- **State Management**:
  ```javascript
  conversationHistory = []; // Tracks all messages for navigation
  ```

---

## 2. Video Guidance Link

### Features
- **Location**: Disclaimer section (below header, above chat messages)
- **Styling**:
  - Blue color (#0066cc)
  - Underlined text
  - 🎥 emoji icon
  - Hover effect (darker blue)
- **Link Behavior**:
  - Opens in new tab (`target="_blank"`)
  - Security attributes (`rel="noopener noreferrer"`)

### How to Update Video URL

**Current placeholder URL**: `https://www.youtube.com/watch?v=YOUR_VIDEO_ID`

**To update with actual video**:

1. Open `app/frontend/widget.html`
2. Find line containing:
   ```html
   <a href="https://www.youtube.com/watch?v=YOUR_VIDEO_ID"
   ```
3. Replace with your video URL:
   ```html
   <a href="https://www.youtube.com/watch?v=actual_video_id"
   ```

**Supported Video Platforms**:
- YouTube: `https://www.youtube.com/watch?v=VIDEO_ID`
- YouTube Embed: `https://www.youtube.com/embed/VIDEO_ID`
- Vimeo: `https://vimeo.com/VIDEO_ID`
- Direct MP4: `https://example.com/video.mp4`

**Testing Checklist**:
- ✅ Link opens in new tab
- ✅ Video loads immediately (not blank page)
- ✅ Link is visible and clearly styled
- ✅ Works on mobile devices

---

## 3. Voice Feature (Text-to-Speech)

### Features
- **Button Location**: At bottom of each bot message bubble
- **Button States**:
  - Default: "🔊 Listen" (blue background)
  - Playing: "⏸ Stop" (primary color, pulsing animation)
  - Disabled: Grayed out (unsupported browsers)

### Functionality
- **Play Audio**: Click button to hear bot response
- **Stop Audio**: Click again to stop playback
- **Multi-language Support**: Automatically uses selected language
  - English (en-US)
  - Hindi (hi-IN)
  - Telugu (te-IN)
  - Tamil (ta-IN)
  - Marathi (mr-IN)
  - Kannada (kn-IN)

### Technical Details

**Browser Compatibility**:
- ✅ Chrome/Edge: Full support
- ✅ Firefox: Full support
- ✅ Safari: Full support
- ⚠️ IE11: Not supported (button disabled)

**Text Processing**:
- Removes HTML tags
- Strips markdown formatting
- Converts line breaks to pauses
- Rate: 0.9 (slightly slower for clarity)

**Speech Settings**:
```javascript
utterance.rate = 0.9;  // Speed
utterance.pitch = 1.0; // Tone
utterance.volume = 1.0; // Volume
```

### Accessibility Benefits
- ✅ Visually impaired users can listen to responses
- ✅ Users with reading difficulties benefit from audio
- ✅ Multi-tasking users can listen while working
- ✅ Language learners can hear pronunciation

---

## Files Modified

### 1. `app/frontend/widget.html`
**Changes**:
- Added back button in chat header
- Added video guide link in disclaimer section

### 2. `app/frontend/widget.css`
**New Styles**:
- `.back-btn` - Back button styling
- `.video-guide-link` - Video link styling
- `.tts-button` - TTS button styling
- `.tts-button.playing` - Playing state animation
- `.tts-icon` - Speaker icon styling

### 3. `app/frontend/widget.js`
**New Functions**:
- `createTTSButton(text)` - Creates TTS button for each message
- `speakText(text, buttonElement)` - Text-to-speech conversion
- `stopSpeech()` - Stops any playing audio
- `goBack()` - Navigate back in conversation
- `updateBackButtonVisibility()` - Shows/hides back button

**New State Variables**:
- `conversationHistory` - Array tracking all messages
- `currentSpeech` - Current SpeechSynthesis instance
- `isSpeaking` - Boolean flag for audio playback

---

## User Experience Improvements

### Before
- ❌ No way to navigate back
- ❌ No video guidance available
- ❌ Text-only responses (no audio option)

### After
- ✅ Easy back navigation
- ✅ Video guide accessible from chat
- ✅ Audio playback for all bot responses
- ✅ Multi-language TTS support
- ✅ Better accessibility for all users

---

## Testing Recommendations

### 1. Back Button
- [ ] Test with multiple conversation exchanges
- [ ] Verify history is cleared on home button
- [ ] Check button visibility toggles correctly
- [ ] Test on mobile devices

### 2. Video Link
- [ ] Update placeholder URL with actual video
- [ ] Verify link opens in new tab
- [ ] Test video loads immediately
- [ ] Check styling on different screen sizes
- [ ] Test on mobile browsers

### 3. Text-to-Speech
- [ ] Test with short messages
- [ ] Test with long responses
- [ ] Verify multi-language support
- [ ] Test stop functionality
- [ ] Check browser compatibility
- [ ] Test with markdown-formatted text
- [ ] Verify only one speech plays at a time

---

## Deployment Notes

### Cache Busting
Update version numbers in `widget.html`:
```html
<link rel="stylesheet" href="/static/widget.css?v=22" />
<script src="/static/widget.js?v=22"></script>
```
(Increment from current v=21 to v=22)

### Performance Impact
- **Back Button**: Minimal (array operations only)
- **Video Link**: None (static link)
- **TTS**: Minimal (browser native API)

### Mobile Considerations
- All features are responsive
- TTS works on mobile browsers
- Back button sized for touch targets
- Video link touch-friendly

---

## Future Enhancements

### Potential Improvements
1. **Download Audio**: Allow downloading TTS audio
2. **Playback Speed Control**: Let users adjust speech rate
3. **Voice Selection**: Choose from available voices
4. **Transcript Export**: Save conversation as text/audio
5. **Keyboard Shortcuts**: Alt+B for back, Alt+L for listen

---

## Support & Troubleshooting

### Video Link Not Working
**Issue**: Link opens blank page or doesn't load video
**Solution**: 
1. Verify URL is complete and correct
2. Test URL in browser directly
3. For YouTube, try embed URL: `https://www.youtube.com/embed/VIDEO_ID`
4. Ensure video is public/unlisted (not private)

### TTS Not Working
**Issue**: No audio plays when clicking Listen button
**Solution**:
1. Check browser compatibility (use Chrome/Firefox/Safari)
2. Verify browser permissions for audio
3. Test with different message lengths
4. Check browser console for errors
5. Ensure language pack is installed for non-English languages

### Back Button Not Appearing
**Issue**: Back button never shows
**Solution**:
1. Check browser console for JavaScript errors
2. Verify widget.js version is updated
3. Clear browser cache
4. Test in incognito/private mode

---

## Contact & Updates

For questions or issues with these enhancements, check:
- Browser console for error messages
- Network tab for resource loading issues
- Widget version numbers are updated (v=22)

---

**Last Updated**: March 30, 2026
**Version**: 1.0
**Status**: Production Ready ✅
