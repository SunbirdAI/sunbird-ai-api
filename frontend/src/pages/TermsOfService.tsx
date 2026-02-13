import Header from '../components/Header';
import Footer from '../components/Footer';

export default function TermsOfService() {
  return (
    <div className="min-h-screen bg-white dark:bg-black flex flex-col">
      <Header />
      
      <main className="flex-1 pt-24 pb-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-8">Terms of Service</h1>
          
          <div className="space-y-8 text-gray-700 dark:text-gray-300">
            <div>
              <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-4">Agreement</h2>
              <p className="leading-relaxed">
                By accessing or using the services provided by Sunbird AI, you agree
                to abide by these Terms of Service. These Terms apply to all visitors,
                users, and others who access or use our services.
              </p>
            </div>

            <div>
              <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-4">Use of Services</h2>
              <p className="leading-relaxed">
                Our services, including the WhatsApp translation bot, are provided on
                an "as is" and "as available" basis. Users are solely responsible for
                their use of the services and any consequences thereof.
              </p>
            </div>

            <div>
              <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-4">Intellectual Property</h2>
              <p className="leading-relaxed">
                All intellectual property rights associated with the services provided
                by Sunbird AI, including but not limited to, the WhatsApp translation
                bot, are owned by Sunbird AI. Users are granted a limited,
                non-exclusive, non-transferable license to use the services for
                personal or non-commercial purposes.
              </p>
            </div>

            <div>
              <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-4">Limitation of Liability</h2>
              <p className="leading-relaxed">
                Sunbird AI shall not be liable for any indirect, incidental, special,
                consequential, or punitive damages, or any loss of profits or
                revenues, whether incurred directly or indirectly, or any loss of
                data, use, goodwill, or other intangible losses resulting from (i)
                your access to or use of or inability to access or use the services;
                (ii) any conduct or content of any third party on the services; (iii)
                any content obtained from the services; or (iv) unauthorized access,
                use, or alteration of your transmissions or content.
              </p>
            </div>

            <div>
              <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-4">Changes to Terms of Service</h2>
              <p className="leading-relaxed">
                Sunbird AI reserves the right to update or change these Terms of
                Service at any time. Users will be notified of any changes by posting
                the new Terms of Service on this page.
              </p>
            </div>

            <div>
              <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-4">Contact Us</h2>
              <p className="leading-relaxed">
                If you have any questions about these Terms of Service, please contact
                us at <a href="mailto:info@sunbird.ai" className="text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 underline">info@sunbird.ai</a>
              </p>
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
