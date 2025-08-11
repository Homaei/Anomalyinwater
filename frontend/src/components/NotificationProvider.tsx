import React from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { Snackbar, Alert, Portal, Slide, SlideProps } from '@mui/material';
import { RootState } from '@/store';
import { removeNotification } from '@/store/notificationSlice';

function SlideTransition(props: SlideProps) {
  return <Slide {...props} direction="down" />;
}

interface NotificationProviderProps {
  children: React.ReactNode;
}

const NotificationProvider: React.FC<NotificationProviderProps> = ({ children }) => {
  const dispatch = useDispatch();
  const notifications = useSelector((state: RootState) => state.notifications.notifications);
  
  const currentNotification = notifications[0]; // Show most recent notification

  const handleClose = (id?: string) => {
    if (id) {
      dispatch(removeNotification(id));
    }
  };

  return (
    <>
      {children}
      
      <Portal>
        <Snackbar
          open={Boolean(currentNotification)}
          autoHideDuration={6000}
          onClose={() => handleClose(currentNotification?.id)}
          TransitionComponent={SlideTransition}
          anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
        >
          <Alert
            onClose={() => handleClose(currentNotification?.id)}
            severity={currentNotification?.severity || 'info'}
            variant="filled"
            sx={{ width: '100%' }}
          >
            {currentNotification?.message}
          </Alert>
        </Snackbar>
      </Portal>
    </>
  );
};

export default NotificationProvider;