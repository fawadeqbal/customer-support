-- 002_demo_orders.sql: six demo orders for the lookup_order tool.
-- Dates are relative to the day this runs, so the demo looks current.
INSERT INTO orders VALUES
 ('SE10482931','Shipped','Pulse Wireless Earbuds x1',6499,'Cash on Delivery','Lahore',
   now() - interval '2 days', (now() + interval '1 day')::date,'TCS','TCS-77120934'),
 ('SE10482932','Out for Delivery','Nova X5 Smartphone 128 GB x1',89999,'Card','Karachi',
   now() - interval '3 days', now()::date,'Leopards','LP-5520187'),
 ('SE10482933','Delivered','Brew Coffee Maker x1',18750,'JazzCash','Islamabad',
   now() - interval '8 days', (now() - interval '4 days')::date,'TCS','TCS-77098120'),
 ('SE10482934','Pending','Volt Power Bank x2',8598,'Cash on Delivery','Multan',
   now() - interval '3 hours', (now() + interval '4 days')::date,NULL,NULL),
 ('SE10482935','Returned to Seller','Orbit Smartwatch x1',12999,'Cash on Delivery','Peshawar',
   now() - interval '10 days', NULL,'M&P','MP-3310452'),
 ('SE10482936','Packed','Glow 65" 4K LED TV x1',189999,'Card (6-month installments)','Faisalabad',
   now() - interval '1 day', (now() + interval '3 days')::date,NULL,NULL)
ON CONFLICT (order_no) DO NOTHING;
