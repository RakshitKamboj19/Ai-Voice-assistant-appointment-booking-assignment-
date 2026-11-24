import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, AudioLines, CalendarDays, Check, ChevronRight, CircleHelp, Clock3, Headphones, Mic, MicOff, Phone, PhoneOff, RefreshCw, ShieldCheck, Sparkles, Stethoscope, UserRound } from 'lucide-react'
import { PipecatClient } from '@pipecat-ai/client-js'
import { WebSocketTransport, ProtobufFrameSerializer } from '@pipecat-ai/websocket-transport'

const API = ''
const formatSlot = value => new Date(value).toLocaleString('en-US',{weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})
const todayLabel = new Date().toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'}).toUpperCase()
const cleanSpeechChunk = value => String(value||'').replace(/[*_`#]/g,'').replace(/^\s*[-•]\s*/,'').replace(/\s+/g,' ').trim()
const joinSpeechChunks = (current,next) => !current?next:/^[,.;:!?%)\]}]/.test(next)?`${current}${next}`:`${current} ${next}`

export default function App(){
  const [doctors,setDoctors]=useState([]),[appointments,setAppointments]=useState([]),[transcript,setTranscript]=useState([])
  const [activePage,setActivePage]=useState('overview')
  const [cancelingId,setCancelingId]=useState(null),[notice,setNotice]=useState('')
  const [callState,setCallState]=useState('idle'),[muted,setMuted]=useState(false),[agentSpeaking,setAgentSpeaking]=useState(false),[error,setError]=useState('')
  const clientRef=useRef(null), transcriptEnd=useRef(null), endingCall=useRef(false), mutedRef=useRef(false), botSpeakingRef=useRef(false), botLineRef=useRef(null)
  const refresh=useCallback(async()=>{
    try { const [d,a]=await Promise.all([fetch(`${API}/api/doctors`),fetch(`${API}/api/appointments`)]); if(!d.ok||!a.ok)throw Error('Dashboard service unavailable'); setDoctors(await d.json());setAppointments(await a.json());setError('') }
    catch(e){setError(`${e.message}. Start the backend API to load live data.`)}
  },[])
  useEffect(()=>{refresh();const id=setInterval(refresh,5000);return()=>clearInterval(id)},[refresh])
  useEffect(()=>()=>{try{clientRef.current?.disconnect()}catch{}clientRef.current=null},[])
  useEffect(()=>{transcriptEnd.current?.scrollIntoView({behavior:'smooth'})},[transcript])
  const addLine=useCallback((speaker,text)=>{if(!text)return;setTranscript(lines=>[...lines,{speaker,text,at:new Date()}])},[])
  const startCall=async()=>{
    setError('');setCallState('connecting');setTranscript([]);endingCall.current=false;mutedRef.current=false;botSpeakingRef.current=false;botLineRef.current=null
    try{
      const transport=new WebSocketTransport({serializer:new ProtobufFrameSerializer(),recorderSampleRate:16000,playerSampleRate:24000})
      const client=new PipecatClient({transport,enableMic:true,enableCam:false,callbacks:{
        onConnected:()=>setCallState('connected'),
        onDisconnected:()=>{setCallState('idle');setAgentSpeaking(false);botSpeakingRef.current=false;if(!endingCall.current)setError('The voice call ended unexpectedly. Check the Pipecat backend logs and provider configuration, then try again.')},
        onUserTranscript:data=>{if(data?.text&&data?.final!==false){botLineRef.current=null;addLine('you',data.text)}},
        onBotTtsText:data=>{
          const text=cleanSpeechChunk(data?.text)
          if(!text)return
          let id=botLineRef.current
          if(!id){id=`assistant-${Date.now()}-${Math.random()}`;botLineRef.current=id;setTranscript(lines=>[...lines,{id,speaker:'assistant',text,at:new Date()}]);return}
          setTranscript(lines=>lines.map(line=>line.id===id?{...line,text:joinSpeechChunks(line.text,text)}:line))
        },
        // This browser transport has no acoustic echo cancellation in its
        // recorder configuration. Keep turns half-duplex so speaker output
        // cannot be re-captured as caller speech and interrupt the agent.
        onBotStartedSpeaking:()=>{botSpeakingRef.current=true;setAgentSpeaking(true);if(!mutedRef.current)clientRef.current?.enableMic(false)},
        onBotStoppedSpeaking:()=>{botSpeakingRef.current=false;setAgentSpeaking(false);if(!mutedRef.current)clientRef.current?.enableMic(true)},
        onBotReady:()=>setCallState('connected'),
        onDeviceError:e=>{console.error('Microphone device error:',e);setError(e?.message||'Microphone access failed. Allow microphone access for this site and try again.')},
        onError:e=>{console.error('Pipecat voice error:',e);const detail=e?.data?.message||e?.message||e?.label;setError(detail?`Voice error: ${detail}`:'Voice connection failed. Check the microphone and backend logs.')}
      }})
      clientRef.current=client
      const wsProtocol=window.location.protocol==='https:'?'wss:':'ws:'
      await client.connect({wsUrl:`${wsProtocol}//${window.location.hostname}:7860/ws-client`})
    }catch(e){setCallState('idle');setError(e?.message||'Could not connect to the Pipecat voice agent. Make sure it is running and microphone access is allowed.')}
  }
  const endCall=async()=>{endingCall.current=true;try{await clientRef.current?.disconnect()}catch{}clientRef.current=null;setCallState('idle');setMuted(false);refresh()}
  const cancelAppointment=async appointment=>{
    const when=formatSlot(appointment.starts_at)
    if(!window.confirm(`Cancel the appointment with ${appointment.doctor_name} on ${when}?`))return
    setCancelingId(appointment.id);setNotice('');setError('')
    try{
      const response=await fetch(`${API}/api/appointments/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone:appointment.phone,appointment_id:appointment.id})})
      const result=await response.json()
      if(!response.ok)throw new Error(result.detail||'Could not cancel this appointment.')
      await refresh();setNotice(`Appointment with ${appointment.doctor_name} cancelled.`)
    }catch(e){setError(`${e.message} Please try again.`)}finally{setCancelingId(null)}
  }
  const toggleMute=async()=>{const next=!muted;mutedRef.current=next;setMuted(next);try{await clientRef.current?.enableMic(!next&&!botSpeakingRef.current)}catch{mutedRef.current=!next;setMuted(!next)}}
  const active=callState!=='idle'
  const activeAppointments=appointments.filter(a=>a.status==='booked').length
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Activity size={19}/></div><div><b>careline</b><span>APPOINTMENT DESK</span></div></div>
      <div className="workspace-label">WORKSPACE</div><button className={`nav-item ${activePage==='overview'?'selected':''}`} onClick={()=>setActivePage('overview')}><Activity size={17}/> Overview</button><button className={`nav-item ${activePage==='appointments'?'selected':''}`} onClick={()=>setActivePage('appointments')}><CalendarDays size={17}/> Appointments <span className="nav-count">{activeAppointments}</span></button>
      <div className="sidebar-bottom"><div className="secure-card"><ShieldCheck size={17}/><div><b>Private by design</b><span>Phone number only. No login or caller ID.</span></div></div><div className="profile"><div className="profile-avatar">CD</div><div><b>Careline Demo</b><span>Clinic workspace</span></div><CircleHelp size={17}/></div></div>
    </aside>
    <main className="main">
      <header className="topbar"><div className="breadcrumb">Workspace <ChevronRight size={14}/> <b>{activePage==='appointments'?'Appointments':'Overview'}</b></div><div className="top-actions"><span className="today"><span className="live-dot"/> Demo environment</span><button className="icon-button" aria-label="Refresh" onClick={refresh}><RefreshCw size={17}/></button><div className="avatar">CD</div></div></header>
      <div className="content">
        {activePage==='appointments'?<>
          <section className="appointments-page-heading"><div><div className="eyebrow">SCHEDULE</div><h1>Appointments</h1><p>View all scheduled and cancelled appointments.</p></div><span className="doctor-total">{appointments.length} total</span></section>
          {error&&<div className="error-banner">{error}</div>}
          {notice&&<div className="success-banner" role="status">{notice}</div>}
          {appointments.length===0?<div className="panel empty-state appointments-empty"><CalendarDays size={24}/><b>No appointments yet</b><span>Appointments booked through Careline will appear here automatically.</span></div>:<section className="panel appointments-page-list"><div className="appointments-table-head"><span>DOCTOR</span><span>DATE & TIME</span><span>PATIENT PHONE</span><span>STATUS</span><span>ACTION</span></div>{appointments.slice().sort((a,b)=>new Date(a.starts_at)-new Date(b.starts_at)).map(a=><div className="appointments-table-row" key={a.id}><div className="table-doctor"><b>{a.doctor_name}</b><span>{a.speciality}</span></div><span>{formatSlot(a.starts_at)}</span><span>•••• {String(a.phone||'').replace(/\D/g,'').slice(-4)||'—'}</span><span className={`appointment-status ${a.status==='booked'?'is-booked':'is-cancelled'}`}>{a.status==='booked'?'Booked':'Cancelled'}</span><span>{a.status==='booked'?<button className="cancel-appointment-button" disabled={cancelingId===a.id} onClick={()=>cancelAppointment(a)}>{cancelingId===a.id?'Cancelling…':'Cancel appointment'}</button>:<span className="action-dash">—</span>}</span></div>)}</section>}
        </>:<>
        <section className="welcome"><div><div className="eyebrow">{todayLabel}</div><h1>Your appointment desk</h1><p>Manage calls and care schedules from one place.</p></div><div className="welcome-icon"><Stethoscope size={26}/></div></section>
        {error&&<div className="error-banner">{error}</div>}
        <section className="metrics"><Metric label="Active appointments" value={activeAppointments} note="Across all patients" icon={<CalendarDays size={18}/>} color="mint"/><Metric label="Care team" value={doctors.length} note={`${new Set(doctors.map(d=>d.speciality)).size} specialties`} icon={<UserRound size={18}/>} color="blue"/><Metric label="Open time slots" value={doctors.reduce((n,d)=>n+d.available_slots?.length,0)} note="Ready to book" icon={<Clock3 size={18}/>} color="amber"/></section>
        <section className="dashboard-grid">
          <div className="panel call-panel"><div className="panel-heading"><div><div className="eyebrow">VOICE ASSISTANT</div><h2>Start a conversation</h2></div><span className={`status-pill ${active?'status-live':''}`}><span className="status-dot"/>{callState==='connecting'?'Connecting':callState==='connected'?'On call':'Ready'}</span></div>
            <div className={`call-visual ${active?'call-active':''}`}><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="call-core"><AudioLines size={27}/></div><span className="visual-caption">{callState==='connecting'?'Establishing secure audio…':callState==='connected'?(agentSpeaking?'Careline is speaking…':'Listening — speak naturally'):'Your AI care coordinator'}</span></div>
            <div className="call-control-row">{!active?<button className="call-button" onClick={startCall}><Phone size={17} fill="currentColor"/> Start voice call</button>:<><button className={`mute-button ${muted?'muted':''}`} onClick={toggleMute}>{muted?<MicOff size={17}/>:<Mic size={17}/>} {muted?'Unmute':'Mute'}</button><button className="end-button" onClick={endCall}><PhoneOff size={17} fill="currentColor"/> End call</button></>}</div>
            <div className="call-hint"><Sparkles size={14}/> Ask about a doctor, available times, or an existing appointment.</div>
            <div className="transcript"><div className="transcript-header"><span><span className="transcript-dot"/> LIVE TRANSCRIPT</span><span>{transcript.length} messages</span></div><div className="transcript-body">{transcript.length===0?<div className="transcript-empty"><Headphones size={19}/><span>Your conversation will appear here</span><small>Start a voice call to get going</small></div>:transcript.map((line,i)=><div className={`message ${line.speaker==='you'?'from-you':''}`} key={i}><div className="message-avatar">{line.speaker==='you'?'Y':'C'}</div><div><div className="message-meta">{line.speaker==='you'?'You':'Careline'} <time>{line.at.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})}</time></div><p>{line.text}</p></div></div>)}<div ref={transcriptEnd}/></div></div>
          </div>
          <div className="panel appointments-panel"><div className="panel-heading"><div><div className="eyebrow">SCHEDULE</div><h2>Appointments</h2></div><button className="text-button" onClick={()=>setActivePage('appointments')}>View all <ChevronRight size={14}/></button></div>
            {appointments.filter(a=>a.status==='booked').length===0?<div className="empty-state"><CalendarDays size={22}/><b>No upcoming appointments</b><span>New bookings will appear here automatically.</span></div>:<div className="appointment-list">{appointments.filter(a=>a.status==='booked').slice(0,7).map(a=><div className="appointment-row" key={a.id}><div className="date-block"><b>{new Date(a.starts_at).toLocaleDateString('en-US',{day:'2-digit'})}</b><span>{new Date(a.starts_at).toLocaleDateString('en-US',{month:'short'}).toUpperCase()}</span></div><div className="appointment-info"><b>{a.doctor_name}</b><span>{a.speciality} · {formatSlot(a.starts_at).split('·').at(-1)}</span><small>•••• {a.phone.replace(/\D/g,'').slice(-4)}</small></div><span className="booked-tag"><Check size={12}/> Booked</span></div>)}</div>}
            <div className="panel-footer"><span>Updates automatically after each call</span><span className="sync-mark"><RefreshCw size={12}/> Live sync</span></div>
          </div>
        </section>
        <section className="panel doctors-panel"><div className="panel-heading"><div><div className="eyebrow">THE CARE TEAM</div><h2>Doctors & availability</h2></div><span className="doctor-total">{doctors.length} providers</span></div><div className="doctor-grid">{doctors.map(d=><article className="doctor-card" key={d.id}><div className="doctor-top"><div className="doctor-avatar">{d.initials}</div><span className="availability-dot"/></div><h3>{d.name}</h3><div className="speciality">{d.speciality}</div><div className="doctor-location">{d.location}</div><div className="slot-divider"/><div className="slot-label">NEXT AVAILABLE <b>{d.available_slots?.length||0} slots</b></div><div className="slot-chips">{d.available_slots?.slice(0,3).map(s=><span key={s.id}>{formatSlot(s.starts_at)}</span>)}{!d.available_slots?.length&&<span className="no-slots">No openings right now</span>}</div></article>)}</div></section>
        </>}
        <footer><span>Careline Voice Assistant <i>·</i> Powered by Pipecat, Gemini & ElevenLabs</span><span><span className="live-dot"/> All systems operational</span></footer>
      </div>
    </main>
  </div>
}
function Metric({label,value,note,icon,color}){return <div className="metric-card"><div className={`metric-icon ${color}`}>{icon}</div><div className="metric-copy"><span>{label}</span><b>{value}</b><small>{note}</small></div><div className="metric-trend"><span>↗</span></div></div>}
