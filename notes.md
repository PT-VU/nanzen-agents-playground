findings:

Overall I find this data included a lot of information and a lot of different cases. For me to Make this agent run correctly without any further negotiation with financial team, I have to make a lot of assumptions and I will list some of the assumptions here.


data: Besides a lot of different kind of invoice cases, we also have some lines that are missing some important values for example account ID or invoice ID. for example:BIL-5156，andBIL-5204. The second case is obviously an information missing because it was involved in the same invoice ID which with account ID, So I used the invoice ID searched the account ID and filled in this blank. But for the first case there was an mistake of transaction so I assume it should be not attached to any invoice case, So I leave it be an no invoice id situation. 

To have a better performance of this project I think it would be better for us to define What is a normal proper Procedure of an invoiced case and what are the most common seeing abnormal case. So in this agent I did Quite a lot Local definition(assumption) to help the agent give the right judgement quickly and correctly. For example I defined a standard sop of a normal inverse case, and categorised and listed some of the abnormal cases that have been appeared in the data.



left: When I was checking the raw data, I realized that In January 2024 There has been no payment at all. Although I think This kind of monthly payment should be paid every month, I don't think it's this agent's task or responsibility(or authorized) to define there is a missing payment in January 2024. This agent is only responsible for the invoiced cases. So I did not include that part in the report.

And I also noticed that sometimes one invoice case could affect another invoice case or credit case. like INV-2026-MH-027 has been affected by INV-2026-MH-026. （Did not apply credit in Janurary，so moved to Feb） But this is not a serious cross invoice case situation (cause its a delay apply of credit) So I did not add any extra mechanism on this but I wonder does this kind of cross-invoice case situation happens. Do we need to consider about it?



one suggestion to our customer： if every time we are using credit,  we can Put the credit id In the description of the invoice. That will resolve a lot of hidden risks of Mismatching. i see that happens for Second credit case but not for the first credit case. And at the same time the second credit case there is also a “credit applied” row when it was applied but not for credit case one.

And A well-defined SOP of credit case would also help us to have a better understanding of how credit initialization and Apply Works. A clear Trajectory Or note will also decrease the hidden risks.(like the 1854 goodwill adjustment that still open not closed(I count that  as a credit case too))

