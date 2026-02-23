
import asyncio
import os
import sys

# Add current dir to path
sys.path.append(os.getcwd())

async def health_check():
    print("=== AURA SYSTEM SYNC HEALTH CHECK ===")
    
    try:
        from core.container import ServiceContainer
        from core.service_registration import register_all_services
        
        print("1. Registering all services...")
        register_all_services()
        
        print("\n2. Waking container (Asynchronous)...")
        to_wake = [n for n, d in ServiceContainer._services.items() if d.required]
        errors = []
        for name in to_wake:
            try:
                print(f"  Waking {name}...")
                instance = ServiceContainer.get(name)
                if hasattr(instance, 'on_start_async'):
                    await instance.on_start_async()
                print(f"    [✓] {name} online.")
            except Exception as e:
                print(f"    [!] {name} FAILED: {e}")
                import traceback
                traceback.print_exc()
                errors.append(f"{name}: {e}")
        
        if errors:
            print(f"\nSummary: FAILED to wake {len(errors)} services.")
            
        print("\n3. Health Report:")
        report = ServiceContainer.get_health_report()
        print(f"Status: {report['status']}")
        for svc, meta in report['services'].items():
            print(f"  [ {'✓' if meta['status'] == 'healthy' else '!'} ] {svc}: {meta['status']}")
            
        print("\n4. Component Linkage Check:")
        cognitive_engine = ServiceContainer.get("cognitive_engine")
        if cognitive_engine:
            print(f"  - CognitiveEngine online ({type(cognitive_engine)})")
            # Check if wired
            if hasattr(cognitive_engine, 'autonomous_brain') and cognitive_engine.autonomous_brain:
                print("    [✓] Autonomous Brain linked.")
            else:
                print("    [!] Autonomous Brain MISSING.")
        else:
            print("  [!] CognitiveEngine MISSING.")
            
        personality_engine = ServiceContainer.get("personality_engine")
        if personality_engine:
            print(f"  - PersonalityEngine online ({type(personality_engine)})")
        else:
            print("  [!] PersonalityEngine MISSING.")
            
    except Exception as e:
        print(f"\nCRITICAL ERROR during health check: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(health_check())
