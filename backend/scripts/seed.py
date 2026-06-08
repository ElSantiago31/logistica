import asyncio 
from sqlalchemy import text 
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession 
from sqlalchemy.orm import sessionmaker 
async def seed(): 
 e=create_async_engine('postgresql+asyncpg://logistica:logistica_dev_2024@localhost:5432/logistica') 
 S=sessionmaker(e,class_=AsyncSession,expire_on_commit=False) 
 async with S() as db: 
  r=await db.execute(text('SELECT count(*) FROM eps')) 
  print('BEFORE:'+str(r.scalar())) 
  for i,n in enumerate(['Sanitas','Nueva EPS','Sura','Saludvida','Famisanar','Coomeva','Compensar','Medimas']): await db.execute(text('INSERT INTO eps (id,name,code,nit,is_active) VALUES (gen_random_uuid(),:n,:c,:nit,true)'),{'n':n,'c':'EPS%03d'%(i+1),'nit':'900%d'%(100000+i)}) 
  for i,n in enumerate(['Positiva','Colpatria','Bolivar','Sura','Equidad','Colmena','La Previsora']): await db.execute(text('INSERT INTO arl (id,name,code,nit,is_active) VALUES (gen_random_uuid(),:n,:c,:nit,true)'),{'n':n,'c':'ARL%03d'%(i+1),'nit':'800%d'%(100000+i)}) 
  await db.commit() 
  r=await db.execute(text('SELECT count(*) FROM eps')) 
  print('AFTER:'+str(r.scalar())) 
 await e.dispose() 
asyncio.run(seed()) 
